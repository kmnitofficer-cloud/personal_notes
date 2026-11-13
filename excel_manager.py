"""
Excel database management module for Personal Notes Management Web App.
Stores active notes in a central Excel workbook (personal_notes.xlsx) and preserves
all historical notes in a dedicated, permanent audit & backup Excel workbook (personal_notes_backup.xlsx).
When notes are deleted from the active list, they are NEVER deleted from the backup workbook;
instead, they are preserved with a DELETED status, timestamp, and deleter identity.
Features high-performance local caching and non-blocking background Google Drive sync.
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

# Standard Excel Columns for Active Notes
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

# Audit & Backup Excel Columns (Never Deleted, Permanent History)
BACKUP_COLUMNS = [
    "Note ID",
    "Status",              # "ACTIVE" or "DELETED"
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
    "Deleted Date",
    "Deleted By",
]


class ExcelNotesManager:
    """
    High-performance, thread-safe manager for the central Excel database and
    permanent backup archive. Enforces user isolation, zero data loss, and
    background Google Drive synchronization.
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
        self.local_backup_path = os.path.join(
            os.path.dirname(self.local_excel_path), "personal_notes_backup.xlsx"
        )
        self.lock_path = self.local_excel_path + ".lock"
        self.backup_lock_path = self.local_backup_path + ".lock"
        os.makedirs(os.path.dirname(self.local_excel_path), exist_ok=True)

        self._thread_lock = threading.RLock()
        self._sync_lock = threading.Lock()
        self._is_syncing = False

        self.drive_manager = drive_manager or GoogleDriveManager(file_name="personal_notes.xlsx")
        self.backup_drive_manager = GoogleDriveManager(file_name="personal_notes_backup.xlsx")

        self._ensure_workbook_exists()

    def _clean_active_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sanitizes and enforces standard schema for active notes."""
        if df.empty:
            return pd.DataFrame(columns=COLUMNS)
        clean = df.copy()
        if "Selection 1" in clean.columns and "Customer Name" not in clean.columns:
            clean["Customer Name"] = clean["Selection 1"]
        if "Selection 2" in clean.columns and "Farm Name with Code" not in clean.columns:
            clean["Farm Name with Code"] = clean["Selection 2"]
        clean["Selection 1"] = clean.get("Customer Name", "")
        clean["Selection 2"] = clean.get("Farm Name with Code", "")

        for col in COLUMNS:
            if col not in clean.columns:
                clean[col] = ""

        clean = clean[COLUMNS].fillna("")
        clean["User UID"] = clean["User UID"].astype(str)
        clean["Note ID"] = clean["Note ID"].astype(str)
        return clean

    def _clean_backup_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sanitizes and enforces standard schema for backup notes."""
        if df.empty:
            return pd.DataFrame(columns=BACKUP_COLUMNS)
        clean = df.copy()
        if "Selection 1" in clean.columns and "Customer Name" not in clean.columns:
            clean["Customer Name"] = clean["Selection 1"]
        if "Selection 2" in clean.columns and "Farm Name with Code" not in clean.columns:
            clean["Farm Name with Code"] = clean["Selection 2"]
        clean["Selection 1"] = clean.get("Customer Name", "")
        clean["Selection 2"] = clean.get("Farm Name with Code", "")
        if "Status" not in clean.columns:
            clean["Status"] = "ACTIVE"

        for col in BACKUP_COLUMNS:
            if col not in clean.columns:
                clean[col] = ""

        clean = clean[BACKUP_COLUMNS].fillna("")
        clean["User UID"] = clean["User UID"].astype(str)
        clean["Note ID"] = clean["Note ID"].astype(str)
        clean["Status"] = clean["Status"].replace("", "ACTIVE")
        return clean

    def _ensure_workbook_exists(self):
        """Ensures that both active and backup Excel workbooks exist locally and in Drive."""
        with self._thread_lock:
            with FileLock(self.lock_path, timeout=10):
                # 1. Try downloading active workbook from Drive if connected
                if self.drive_manager and self.drive_manager.is_connected:
                    try:
                        self.drive_manager.download_excel(self.local_excel_path)
                    except Exception as e:
                        logger.warning(f"Could not download active workbook from Drive: {e}")

                # 2. Try downloading backup workbook from Drive if connected
                if self.backup_drive_manager and self.backup_drive_manager.is_connected:
                    try:
                        self.backup_drive_manager.download_excel(self.local_backup_path)
                    except Exception as e:
                        logger.warning(f"Could not download backup workbook from Drive: {e}")

                # 3. Read or create active DataFrame
                active_df = self._read_dataframe()

                # 4. Read or create backup DataFrame
                backup_df = self._read_backup_dataframe()

                # If backup is empty but active has notes, seed backup with active notes
                if backup_df.empty and not active_df.empty:
                    seed_backup = active_df.copy()
                    seed_backup["Status"] = "ACTIVE"
                    seed_backup["Deleted Date"] = ""
                    seed_backup["Deleted By"] = ""
                    backup_df = self._clean_backup_df(seed_backup)

                # Save both locally if files are missing or updated
                if not os.path.exists(self.local_excel_path) or not os.path.exists(self.local_backup_path):
                    self._save_both_local(active_df, backup_df)

    def _read_dataframe(self) -> pd.DataFrame:
        """Reads active notes from the Excel workbook."""
        if not os.path.exists(self.local_excel_path):
            return pd.DataFrame(columns=COLUMNS)

        try:
            with pd.ExcelFile(self.local_excel_path, engine="openpyxl") as xl:
                sheet = "Active_Notes" if "Active_Notes" in xl.sheet_names else 0
                df = pd.read_excel(xl, sheet_name=sheet)
                return self._clean_active_df(df)
        except Exception as e:
            logger.error(f"Error reading active Excel file {self.local_excel_path}: {e}")
            return pd.DataFrame(columns=COLUMNS)

    def _read_backup_dataframe(self) -> pd.DataFrame:
        """Reads permanent audit & backup notes from standalone file or sheet."""
        if os.path.exists(self.local_backup_path):
            try:
                with pd.ExcelFile(self.local_backup_path, engine="openpyxl") as xl:
                    df = pd.read_excel(xl, sheet_name=0)
                    return self._clean_backup_df(df)
            except Exception as e:
                logger.error(f"Error reading backup file {self.local_backup_path}: {e}")

        # Fallback to Audit_Backup_History sheet inside main workbook if present
        if os.path.exists(self.local_excel_path):
            try:
                with pd.ExcelFile(self.local_excel_path, engine="openpyxl") as xl:
                    if "Audit_Backup_History" in xl.sheet_names:
                        df = pd.read_excel(xl, sheet_name="Audit_Backup_History")
                        return self._clean_backup_df(df)
            except Exception as e:
                logger.warning(f"Could not read Audit_Backup_History sheet: {e}")

        return pd.DataFrame(columns=BACKUP_COLUMNS)

    def _save_both_local(self, active_df: pd.DataFrame, backup_df: pd.DataFrame):
        """Writes both active and backup DataFrames to disk atomically."""
        clean_active = self._clean_active_df(active_df)
        clean_backup = self._clean_backup_df(backup_df)

        # 1. Save main active workbook (contains Active_Notes + Audit_Backup_History sheet)
        with pd.ExcelWriter(self.local_excel_path, engine="openpyxl") as writer:
            clean_active.to_excel(writer, sheet_name="Active_Notes", index=False)
            clean_backup.to_excel(writer, sheet_name="Audit_Backup_History", index=False)

        # 2. Save standalone permanent backup workbook (personal_notes_backup.xlsx)
        with FileLock(self.backup_lock_path, timeout=5):
            clean_backup.to_excel(self.local_backup_path, index=False, engine="openpyxl")

    def _trigger_background_drive_sync(self):
        """Dispatches an asynchronous thread to upload both files to Google Drive."""
        def _worker():
            with self._sync_lock:
                # 1. Sync personal_notes.xlsx
                if self.drive_manager and self.drive_manager.is_connected:
                    try:
                        res1 = self.drive_manager.upload_excel(self.local_excel_path)
                        if res1:
                            logger.info(f"Background Drive sync: personal_notes.xlsx updated (ID: {res1})")
                    except Exception as err:
                        logger.error(f"Background upload error for personal_notes.xlsx: {err}")

                # 2. Sync personal_notes_backup.xlsx
                if self.backup_drive_manager and self.backup_drive_manager.is_connected:
                    try:
                        res2 = self.backup_drive_manager.upload_excel(self.local_backup_path)
                        if res2:
                            logger.info(f"Background Drive sync: personal_notes_backup.xlsx updated (ID: {res2})")
                    except Exception as err:
                        logger.error(f"Background upload error for personal_notes_backup.xlsx: {err}")

        sync_thread = threading.Thread(target=_worker, daemon=True)
        sync_thread.start()

    def sync_with_drive_now(self) -> bool:
        """Synchronously forces a complete bidirectional sync for active and backup files."""
        synced_any = False
        with self._thread_lock:
            with FileLock(self.lock_path, timeout=15):
                try:
                    if self.drive_manager and self.drive_manager.is_connected:
                        self.drive_manager._find_or_prepare_drive_file()
                        self.drive_manager.download_excel(self.local_excel_path)
                        res1 = self.drive_manager.upload_excel(self.local_excel_path)
                        if res1:
                            synced_any = True

                    if self.backup_drive_manager and self.backup_drive_manager.is_connected:
                        self.backup_drive_manager._find_or_prepare_drive_file()
                        self.backup_drive_manager.download_excel(self.local_backup_path)
                        res2 = self.backup_drive_manager.upload_excel(self.local_backup_path)
                        if res2:
                            synced_any = True
                except Exception as e:
                    logger.error(f"Manual Drive sync error: {e}")

        return synced_any

    def get_notes_for_user(self, user_uid: str, force_remote_sync: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieves all active notes belonging strictly to the specified user UID.
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
        Adds a new note record to both the active workbook and the permanent backup workbook.
        Fast instant save with background Google Drive synchronization.
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
                active_df = self._read_dataframe()
                backup_df = self._read_backup_dataframe()

                # Add to active notes
                new_row_df = pd.DataFrame([new_record])
                active_df = pd.concat([active_df, new_row_df], ignore_index=True)

                # Add to permanent backup history (Status: ACTIVE)
                backup_record = dict(new_record)
                backup_record["Status"] = "ACTIVE"
                backup_record["Deleted Date"] = ""
                backup_record["Deleted By"] = ""
                backup_row_df = pd.DataFrame([backup_record])
                backup_df = pd.concat([backup_df, backup_row_df], ignore_index=True)

                # Save both files and trigger cloud sync
                self._save_both_local(active_df, backup_df)
                self._trigger_background_drive_sync()
                logger.info(f"Added note {note_id} for user {user_uid} (Active + Permanent Backup)")

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

    def delete_note(self, note_id: str, user_uid: str, username: str = "") -> bool:
        """
        Deletes a note from the active list, but PERMANENTLY PRESERVES it in the backup workbook
        marked with Status = 'DELETED', the exact deletion timestamp, and the deleter's username.
        No data is ever lost.
        """
        if not note_id or not user_uid:
            raise ValueError("Note ID and User UID are required.")

        user_uid_str = str(user_uid).strip()
        note_id_str = str(note_id).strip()

        with self._thread_lock:
            with FileLock(self.lock_path, timeout=5):
                active_df = self._read_dataframe()
                mask = active_df["Note ID"] == note_id_str
                if not mask.any():
                    raise KeyError(f"Note with ID {note_id_str} not found.")

                row = active_df[mask].iloc[0]
                if str(row["User UID"]).strip() != user_uid_str:
                    logger.warning(
                        f"Security alert: User {user_uid_str} attempted to delete note {note_id_str} owned by {row['User UID']}"
                    )
                    raise PermissionError("Access denied: You do not have permission to delete this note.")

                deleted_note_record = dict(row)

                # 1. Remove from active notes DataFrame
                active_df = active_df[~mask]

                # 2. Update or preserve in permanent backup DataFrame (NEVER DELETED)
                backup_df = self._read_backup_dataframe()
                backup_mask = backup_df["Note ID"] == note_id_str
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                deleter_name = username or str(row.get("Username", "")) or user_uid_str

                if backup_mask.any():
                    backup_df.loc[backup_mask, "Status"] = "DELETED"
                    backup_df.loc[backup_mask, "Deleted Date"] = now_str
                    backup_df.loc[backup_mask, "Deleted By"] = deleter_name
                else:
                    deleted_note_record["Status"] = "DELETED"
                    deleted_note_record["Deleted Date"] = now_str
                    deleted_note_record["Deleted By"] = deleter_name
                    backup_df = pd.concat([backup_df, pd.DataFrame([deleted_note_record])], ignore_index=True)

                # 3. Save both files and trigger cloud sync
                self._save_both_local(active_df, backup_df)
                self._trigger_background_drive_sync()
                logger.info(
                    f"Note {note_id_str} removed from active list, preserved permanently in backup as DELETED by {deleter_name}"
                )
                return True
