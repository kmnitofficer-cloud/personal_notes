"""
Excel database management module for Personal Notes Management Web App.
Stores all notes in a central Excel workbook with robust file locking and concurrency control,
automatically syncing reads and writes with Google Drive.
"""

import os
import uuid
import logging
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd
from filelock import FileLock, Timeout

from google_drive import GoogleDriveManager

logger = logging.getLogger(__name__)

# Excel Column Definitions
COLUMNS = [
    "Note ID",
    "User UID",
    "Username",
    "Selection 1",
    "Selection 2",
    "Note Content",
    "Created Date",
    "Updated Date",
]


class ExcelNotesManager:
    """
    Thread-safe and process-safe manager for the central Excel database.
    Enforces user UID isolation so users can never view, edit, or delete notes
    belonging to another user.
    """

    def __init__(
        self,
        local_excel_path: Optional[str] = None,
        drive_manager: Optional[GoogleDriveManager] = None,
    ):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.local_excel_path = (
            local_excel_path
            or os.path.join(base_dir, "data", "personal_notes.xlsx")
        )
        self.lock_path = self.local_excel_path + ".lock"
        os.makedirs(os.path.dirname(self.local_excel_path), exist_ok=True)

        self._thread_lock = threading.RLock()
        self.drive_manager = drive_manager or GoogleDriveManager()

        # Initialize the local file if it doesn't exist
        self._ensure_workbook_exists()

    def _ensure_workbook_exists(self):
        """Ensures that the Excel workbook exists locally, downloading from Drive if possible."""
        with self._thread_lock:
            with FileLock(self.lock_path, timeout=10):
                # Try downloading from Google Drive first if live
                if self.drive_manager and self.drive_manager.is_connected:
                    try:
                        self.drive_manager.download_excel(self.local_excel_path)
                    except Exception as e:
                        logger.warning(f"Could not download workbook from Drive during init: {e}")

                # If local file still does not exist, create an empty one with standard columns
                if not os.path.exists(self.local_excel_path):
                    df = pd.DataFrame(columns=COLUMNS)
                    df.to_excel(self.local_excel_path, index=False, engine="openpyxl")
                    logger.info(f"Created new empty Excel workbook at {self.local_excel_path}")

                    # Upload initial workbook to Drive
                    if self.drive_manager and self.drive_manager.is_connected:
                        try:
                            self.drive_manager.upload_excel(self.local_excel_path)
                        except Exception as e:
                            logger.error(f"Failed to upload initial workbook to Drive: {e}")

    def _read_dataframe(self) -> pd.DataFrame:
        """Reads the Excel workbook into a pandas DataFrame."""
        if not os.path.exists(self.local_excel_path):
            return pd.DataFrame(columns=COLUMNS)

        try:
            df = pd.read_excel(self.local_excel_path, engine="openpyxl")
            # Ensure all required columns exist
            for col in COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            # Fill NaNs with empty string
            df = df.fillna("")
            # Cast User UID and Note ID to string
            df["User UID"] = df["User UID"].astype(str)
            df["Note ID"] = df["Note ID"].astype(str)
            return df
        except Exception as e:
            logger.error(f"Error reading Excel file: {e}", exc_info=True)
            return pd.DataFrame(columns=COLUMNS)

    def _save_dataframe(self, df: pd.DataFrame):
        """Saves DataFrame to local Excel and synchronizes to Google Drive."""
        # Ensure correct column order
        clean_df = df[COLUMNS].copy()
        clean_df.to_excel(self.local_excel_path, index=False, engine="openpyxl")

        # Sync to Google Drive
        if self.drive_manager and self.drive_manager.is_connected:
            try:
                self.drive_manager.upload_excel(self.local_excel_path)
            except Exception as e:
                logger.error(f"Failed to sync updated Excel to Drive: {e}")

    def get_notes_for_user(self, user_uid: str) -> List[Dict[str, Any]]:
        """
        Retrieves all notes belonging strictly to the specified user UID.
        Guarantees that notes from other users are completely excluded.
        """
        if not user_uid:
            return []

        user_uid_str = str(user_uid).strip()

        with self._thread_lock:
            try:
                with FileLock(self.lock_path, timeout=10):
                    # Pull latest state from Drive if connected
                    if self.drive_manager and self.drive_manager.is_connected:
                        self.drive_manager.download_excel(self.local_excel_path)

                    df = self._read_dataframe()
                    if df.empty:
                        return []

                    # Filter strictly by User UID
                    user_df = df[df["User UID"] == user_uid_str].copy()
                    if user_df.empty:
                        return []

                    # Sort by Updated Date descending, or Created Date
                    user_df["SortKey"] = user_df["Updated Date"].where(
                        user_df["Updated Date"] != "", user_df["Created Date"]
                    )
                    user_df = user_df.sort_values(by="SortKey", ascending=False)

                    notes = []
                    for _, row in user_df.iterrows():
                        notes.append({
                            "note_id": str(row["Note ID"]),
                            "user_uid": str(row["User UID"]),
                            "username": str(row["Username"]),
                            "selection1": str(row["Selection 1"]),
                            "selection2": str(row["Selection 2"]),
                            "content": str(row["Note Content"]),
                            "created_date": str(row["Created Date"]),
                            "updated_date": str(row["Updated Date"]),
                        })
                    return notes
            except Timeout:
                logger.error("File lock timeout while reading notes")
                return []
            except Exception as e:
                logger.error(f"Error fetching notes for user {user_uid_str}: {e}")
                return []

    def add_note(
        self,
        user_uid: str,
        username: str,
        selection1: str,
        selection2: str,
        content: str,
    ) -> Dict[str, Any]:
        """
        Adds a new note record to the Excel workbook for the authenticated user.
        Preserves all existing data.
        """
        if not user_uid or not str(user_uid).strip():
            raise ValueError("Authenticated User UID is required.")

        content_clean = str(content or "").strip()
        if not content_clean:
            raise ValueError("Note content cannot be empty.")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        note_id = f"note_{uuid.uuid4().hex[:10]}"

        new_record = {
            "Note ID": note_id,
            "User UID": str(user_uid).strip(),
            "Username": str(username or "").strip(),
            "Selection 1": str(selection1 or "General").strip(),
            "Selection 2": str(selection2 or "Medium").strip(),
            "Note Content": content_clean,
            "Created Date": now_str,
            "Updated Date": now_str,
        }

        with self._thread_lock:
            with FileLock(self.lock_path, timeout=15):
                # Pull latest version first to prevent overwriting concurrent external updates
                if self.drive_manager and self.drive_manager.is_connected:
                    self.drive_manager.download_excel(self.local_excel_path)

                df = self._read_dataframe()
                new_row_df = pd.DataFrame([new_record])
                df = pd.concat([df, new_row_df], ignore_index=True)
                self._save_dataframe(df)
                logger.info(f"Added note {note_id} for user {user_uid}")

        return {
            "note_id": note_id,
            "user_uid": str(user_uid).strip(),
            "username": str(username).strip(),
            "selection1": str(selection1 or "General").strip(),
            "selection2": str(selection2 or "Medium").strip(),
            "content": content_clean,
            "created_date": now_str,
            "updated_date": now_str,
        }

    def update_note(
        self,
        note_id: str,
        user_uid: str,
        selection1: str,
        selection2: str,
        content: str,
    ) -> bool:
        """
        Updates an existing note belonging to the specified user UID.
        Raises PermissionError if the note does not belong to the user.
        """
        if not note_id or not user_uid:
            raise ValueError("Note ID and User UID are required.")

        content_clean = str(content or "").strip()
        if not content_clean:
            raise ValueError("Note content cannot be empty.")

        user_uid_str = str(user_uid).strip()
        note_id_str = str(note_id).strip()

        with self._thread_lock:
            with FileLock(self.lock_path, timeout=15):
                if self.drive_manager and self.drive_manager.is_connected:
                    self.drive_manager.download_excel(self.local_excel_path)

                df = self._read_dataframe()
                mask = df["Note ID"] == note_id_str
                if not mask.any():
                    raise KeyError(f"Note with ID {note_id_str} not found.")

                row = df[mask].iloc[0]
                if str(row["User UID"]).strip() != user_uid_str:
                    logger.warning(
                        f"Security alert: User {user_uid_str} attempted to edit note {note_id_str} owned by {row['User UID']}"
                    )
                    raise PermissionError("Access denied: You do not have permission to edit this note.")

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                df.loc[mask, "Selection 1"] = str(selection1 or "General").strip()
                df.loc[mask, "Selection 2"] = str(selection2 or "Medium").strip()
                df.loc[mask, "Note Content"] = content_clean
                df.loc[mask, "Updated Date"] = now_str

                self._save_dataframe(df)
                logger.info(f"Updated note {note_id_str} for user {user_uid_str}")
                return True

    def delete_note(self, note_id: str, user_uid: str) -> bool:
        """
        Deletes a note belonging to the specified user UID.
        Raises PermissionError if the note belongs to another user.
        """
        if not note_id or not user_uid:
            raise ValueError("Note ID and User UID are required.")

        user_uid_str = str(user_uid).strip()
        note_id_str = str(note_id).strip()

        with self._thread_lock:
            with FileLock(self.lock_path, timeout=15):
                if self.drive_manager and self.drive_manager.is_connected:
                    self.drive_manager.download_excel(self.local_excel_path)

                df = self._read_dataframe()
                mask = df["Note ID"] == note_id_str
                if not mask.any():
                    raise KeyError(f"Note with ID {note_id_str} not found.")

                row = df[mask].iloc[0]
                if str(row["User UID"]).strip() != user_uid_str:
                    logger.warning(
                        f"Security alert: User {user_uid_str} attempted to delete note {note_id_str} owned by {row['User UID']}"
                    )
                    raise PermissionError("Access denied: You do not have permission to delete this note.")

                df = df[~mask]
                self._save_dataframe(df)
                logger.info(f"Deleted note {note_id_str} for user {user_uid_str}")
                return True

