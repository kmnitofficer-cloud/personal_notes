"""
Excel database management module for Personal Notes Management Web App.
Stores notes in a central Excel workbook with robust file locking and concurrency control.
Features high-performance local caching with background synchronization to Google Drive
to eliminate UI latency when adding or deleting notes.
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

# Standard Excel Columns
COLUMNS = [
    "Note ID",
    "User UID",
    "Username",
    "Zone",
    "Customer Name",
    "Farm Name with Code",
    "Selection 1",
    "Selection 2",
    "Note Content",
    "Created Date",
    "Updated Date",
]


class ExcelNotesManager:
    """
    High-performance, thread-safe manager for the central Excel database.
    Enforces user UID isolation and background Google Drive synchronization.
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
        self._sync_lock = threading.Lock()
        self._is_syncing = False
        self._pending_sync = False

        self.drive_manager = drive_manager or GoogleDriveManager()
        self._ensure_workbook_exists()

    def _ensure_workbook_exists(self):
        """Ensures that the Excel workbook exists locally, downloading from Drive if possible."""
        with self._thread_lock:
            with FileLock(self.lock_path, timeout=10):
                if self.drive_manager and self.drive_manager.is_connected:
                    try:
                        self.drive_manager.download_excel(self.local_excel_path)
                    except Exception as e:
                        logger.warning(f"Could not download workbook from Drive during init: {e}")

                if not os.path.exists(self.local_excel_path):
                    df = pd.DataFrame(columns=COLUMNS)
                    df.to_excel(self.local_excel_path, index=False, engine="openpyxl")
                    logger.info(f"Created new empty Excel workbook at {self.local_excel_path}")

                # Ensure remote file exists
                if self.drive_manager and self.drive_manager.is_connected and not self.drive_manager.file_id:
                    try:
                        self.drive_manager.upload_excel(self.local_excel_path)
                        logger.info(f"Uploaded workbook to Google Drive (ID: {self.drive_manager.file_id})")
                    except Exception as e:
                        logger.error(f"Failed to upload initial workbook to Drive: {e}")

    def _read_dataframe(self) -> pd.DataFrame:
        """Reads the Excel workbook into a pandas DataFrame."""
        if not os.path.exists(self.local_excel_path):
            return pd.DataFrame(columns=COLUMNS)

        try:
            df = pd.read_excel(self.local_excel_path, engine="openpyxl")
            if "Selection 1" in df.columns and "Customer Name" not in df.columns:
                df["Customer Name"] = df["Selection 1"]
            if "Selection 2" in df.columns and "Farm Name with Code" not in df.columns:
                df["Farm Name with Code"] = df["Selection 2"]

            for col in COLUMNS:
                if col not in df.columns:
                    df[col] = ""

            df = df.fillna("")
            df["User UID"] = df["User UID"].astype(str)
            df["Note ID"] = df["Note ID"].astype(str)
            return df
        except Exception as e:
            logger.error(f"Error reading Excel file: {e}", exc_info=True)
            return pd.DataFrame(columns=COLUMNS)

    def _trigger_background_drive_sync(self):
        """Dispatches an asynchronous thread to upload to Google Drive without blocking the UI."""
        if not self.drive_manager or not self.drive_manager.is_connected:
            return

        def _worker():
            with self._sync_lock:
                try:
                    logger.info("Background Google Drive sync started...")
                    res = self.drive_manager.upload_excel(self.local_excel_path)
                    if res:
                        logger.info(f"Background Google Drive sync complete (File ID: {res})")
                except Exception as err:
                    logger.error(f"Background Google Drive sync error: {err}")

        sync_thread = threading.Thread(target=_worker, daemon=True)
        sync_thread.start()

    def sync_with_drive_now(self) -> bool:
        """Synchronously downloads and uploads to force a complete bidirectional sync."""
        if not self.drive_manager or not self.drive_manager.is_connected:
            return False

        with self._thread_lock:
            with FileLock(self.lock_path, timeout=15):
                try:
                    # Download latest updates
                    self.drive_manager._find_or_prepare_drive_file()
                    self.drive_manager.download_excel(self.local_excel_path)
                    # Upload local changes
                    res = self.drive_manager.upload_excel(self.local_excel_path)
                    return bool(res)
                except Exception as e:
                    logger.error(f"Manual Drive sync failed: {e}")
                    return False

    def _save_dataframe(self, df: pd.DataFrame):
        """Saves DataFrame locally in milliseconds and dispatches background Google Drive sync."""
        clean_df = df.copy()
        clean_df["Selection 1"] = clean_df["Customer Name"]
        clean_df["Selection 2"] = clean_df["Farm Name with Code"]

        for col in COLUMNS:
            if col not in clean_df.columns:
                clean_df[col] = ""

        clean_df = clean_df[COLUMNS]
        # Instant local save
        clean_df.to_excel(self.local_excel_path, index=False, engine="openpyxl")

        # Non-blocking background upload
        self._trigger_background_drive_sync()

    def get_notes_for_user(self, user_uid: str, force_remote_sync: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieves all notes belonging strictly to the specified user UID.
        Fast local retrieval eliminates latency.
        """
        if not user_uid:
            return []

        user_uid_str = str(user_uid).strip()

        with self._thread_lock:
            try:
                with FileLock(self.lock_path, timeout=5):
                    if force_remote_sync and self.drive_manager and self.drive_manager.is_connected:
                        self.drive_manager.download_excel(self.local_excel_path)

                    df = self._read_dataframe()
                    if df.empty:
                        return []

                    user_df = df[df["User UID"] == user_uid_str].copy()
                    if user_df.empty:
                        return []

                    user_df["SortKey"] = user_df["Updated Date"].where(
                        user_df["Updated Date"] != "", user_df["Created Date"]
                    )
                    user_df = user_df.sort_values(by="SortKey", ascending=False)

                    notes = []
                    for _, row in user_df.iterrows():
                        cust = str(row.get("Customer Name") or row.get("Selection 1", ""))
                        farm = str(row.get("Farm Name with Code") or row.get("Selection 2", ""))
                        notes.append({
                            "note_id": str(row["Note ID"]),
                            "user_uid": str(row["User UID"]),
                            "username": str(row["Username"]),
                            "zone": str(row.get("Zone", "")),
                            "customer_name": cust,
                            "farm_name": farm,
                            "selection1": cust,
                            "selection2": farm,
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
        customer_name: str,
        farm_name: str,
        content: str,
        zone: str = "",
    ) -> Dict[str, Any]:
        """
        Adds a new note record to the Excel workbook for the authenticated user.
        Fast instant save with background Google Drive upload.
        """
        if not user_uid or not str(user_uid).strip():
            raise ValueError("Authenticated User UID is required.")

        content_clean = str(content or "").strip()
        if not content_clean:
            raise ValueError("Note content cannot be empty.")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        note_id = f"note_{uuid.uuid4().hex[:10]}"

        cust_clean = str(customer_name or "").strip()
        farm_clean = str(farm_name or "").strip()
        zone_clean = str(zone or "").strip()

        new_record = {
            "Note ID": note_id,
            "User UID": str(user_uid).strip(),
            "Username": str(username or "").strip(),
            "Zone": zone_clean,
            "Customer Name": cust_clean,
            "Farm Name with Code": farm_clean,
            "Selection 1": cust_clean,
            "Selection 2": farm_clean,
            "Note Content": content_clean,
            "Created Date": now_str,
            "Updated Date": now_str,
        }

        with self._thread_lock:
            with FileLock(self.lock_path, timeout=5):
                df = self._read_dataframe()
                new_row_df = pd.DataFrame([new_record])
                df = pd.concat([df, new_row_df], ignore_index=True)
                self._save_dataframe(df)
                logger.info(f"Added note {note_id} for user {user_uid}")

        return {
            "note_id": note_id,
            "user_uid": str(user_uid).strip(),
            "username": str(username).strip(),
            "zone": zone_clean,
            "customer_name": cust_clean,
            "farm_name": farm_clean,
            "selection1": cust_clean,
            "selection2": farm_clean,
            "content": content_clean,
            "created_date": now_str,
            "updated_date": now_str,
        }

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
            with FileLock(self.lock_path, timeout=5):
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
