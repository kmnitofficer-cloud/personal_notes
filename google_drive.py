"""
Google Drive integration module for Personal Notes Management Web App.
Handles connecting to Google Drive API, searching, downloading, and uploading
the Excel workbook (personal_notes.xlsx) using Google Cloud Service Account credentials.
"""

import os
import io
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Constants
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
]
EXCEL_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DEFAULT_FILE_NAME = "personal_notes.xlsx"


class GoogleDriveManager:
    """
    Manages operations on Google Drive for storing and synchronizing
    the Excel database workbook.
    """

    def __init__(
        self,
        service_account_path: Optional[str] = None,
        folder_id: Optional[str] = None,
        file_name: str = DEFAULT_FILE_NAME,
    ):
        # Check Streamlit secrets first for folder_id
        secret_folder = None
        try:
            import streamlit as st
            if hasattr(st, "secrets") and "GOOGLE_DRIVE_FOLDER_ID" in st.secrets:
                secret_folder = str(st.secrets["GOOGLE_DRIVE_FOLDER_ID"]).strip()
        except Exception:
            pass

        self.file_name = file_name
        self.folder_id = folder_id or secret_folder or os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        default_path = os.path.join(base_dir, "config", "service_account.json")
        env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if env_path and not os.path.isabs(env_path):
            candidate = os.path.join(base_dir, env_path)
            if os.path.exists(candidate):
                env_path = candidate

        self.service_account_path = service_account_path or env_path or default_path
        self.service = None
        self.file_id = None
        self.is_connected = False
        self.status_message = "Initializing..."

        self._initialize_service()

    def _initialize_service(self):
        """Attempts to initialize the Google Drive API client."""
        try:
            # Check Streamlit secrets first
            credentials = None
            try:
                import streamlit as st
                if hasattr(st, "secrets"):
                    for s_key in ["gcp_service_account", "firebase_service_account", "service_account"]:
                        if s_key in st.secrets:
                            from google.oauth2 import service_account
                            info = dict(st.secrets[s_key])
                            credentials = service_account.Credentials.from_service_account_info(
                                info, scopes=SCOPES
                            )
                            logger.info(f"Loaded Google credentials from st.secrets['{s_key}']")
                            break
            except Exception as sec_err:
                logger.warning(f"Error loading credentials from st.secrets: {sec_err}")

            if credentials is None:
                if os.path.exists(self.service_account_path):
                    try:
                        import json
                        with open(self.service_account_path, "r", encoding="utf-8") as f:
                            account_data = json.load(f)
                        # Check if it contains actual keys rather than placeholders
                        pk = account_data.get("private_key", "")
                        if "YOUR_PRIVATE_KEY_HERE" in pk or len(pk) < 100:
                            self.status_message = "Template service_account.json detected. Local mode active."
                            logger.info(self.status_message)
                        else:
                            from google.oauth2 import service_account
                            credentials = service_account.Credentials.from_service_account_info(
                                account_data, scopes=SCOPES
                            )
                            logger.info(f"Loaded credentials from {self.service_account_path}")
                    except Exception as e:
                        self.status_message = f"Could not load service account: {e}. Local mode active."
                        logger.info(self.status_message)
                else:
                    self.status_message = f"Service account file not found at {self.service_account_path}. Local mode active."


            if credentials:
                from googleapiclient.discovery import build
                self.service = build("drive", "v3", credentials=credentials, cache_discovery=False)
                self.is_connected = True
                self.status_message = "Connected to Google Drive API"
                logger.info(self.status_message)
                self._find_or_prepare_drive_file()
            else:
                self.is_connected = False
                logger.warning(
                    f"Google Drive credentials not available. {self.status_message}"
                )

        except Exception as e:
            self.is_connected = False
            self.status_message = f"Google Drive connection error: {str(e)}"
            logger.error(self.status_message, exc_info=True)

    def _find_or_prepare_drive_file(self) -> Optional[str]:
        """Searches for existing personal_notes.xlsx in Drive."""
        if not self.is_connected or not self.service:
            return None

        # Auto-detect shared folder if folder_id is not explicitly provided
        if not self.folder_id:
            try:
                f_resp = (
                    self.service.files()
                    .list(
                        q="mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                        fields="files(id, name)",
                    )
                    .execute()
                )
                folders = f_resp.get("files", [])
                if folders:
                    self.folder_id = folders[0]["id"]
                    logger.info(
                        f"Auto-detected Google Drive folder: '{folders[0]['name']}' (ID: {self.folder_id})"
                    )
            except Exception as e:
                logger.warning(f"Could not auto-detect shared folder: {e}")

        try:
            query = f"name = '{self.file_name}' and trashed = false"
            if self.folder_id:
                query += f" and '{self.folder_id}' in parents"

            response = (
                self.service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="files(id, name, modifiedTime, size)",
                )
                .execute()
            )

            files = response.get("files", [])
            if files:
                self.file_id = files[0]["id"]
                logger.info(f"Found existing Drive file with ID: {self.file_id}")
                return self.file_id
            else:
                logger.info("File not found on Drive. Will be created on initial save.")
                self.file_id = None
                return None
        except Exception as e:
            logger.error(f"Error querying Drive for {self.file_name}: {e}")
            return None

    def download_excel(self, local_destination_path: str) -> bool:
        """
        Downloads personal_notes.xlsx from Google Drive to the local path.
        Returns True if downloaded or up to date, False otherwise.
        """
        if not self.is_connected or not self.service:
            logger.debug("Drive not connected; using local file directly.")
            return False

        if not self.file_id:
            self._find_or_prepare_drive_file()

        if not self.file_id:
            logger.info("No remote Drive file exists yet to download.")
            return False

        try:
            from googleapiclient.http import MediaIoBaseDownload

            request = self.service.files().get_media(fileId=self.file_id)
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request, chunksize=1024 * 1024)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            buffer.seek(0)
            os.makedirs(os.path.dirname(os.path.abspath(local_destination_path)), exist_ok=True)
            with open(local_destination_path, "wb") as f:
                f.write(buffer.read())

            logger.info(f"Successfully downloaded {self.file_name} from Drive.")
            return True
        except Exception as e:
            logger.error(f"Failed to download {self.file_name} from Drive: {e}")
            return False

    def upload_excel(self, local_source_path: str) -> Optional[str]:
        """
        Uploads or updates the local personal_notes.xlsx file to Google Drive.
        Returns the Drive file ID or None on failure/local mode.
        """
        if not os.path.exists(local_source_path):
            raise FileNotFoundError(f"Local file does not exist: {local_source_path}")

        if not self.is_connected or not self.service:
            logger.debug("Drive not connected; saved locally only.")
            return None

        try:
            from googleapiclient.http import MediaFileUpload

            media = MediaFileUpload(
                local_source_path,
                mimetype=EXCEL_MIMETYPE,
                resumable=True,
            )

            # Check if file exists on Drive if file_id is not yet cached
            if not self.file_id:
                self._find_or_prepare_drive_file()

            if self.file_id:
                # Update existing file (works without service account storage quota issues)
                updated_file = (
                    self.service.files()
                    .update(
                        fileId=self.file_id,
                        media_body=media,
                        fields="id, modifiedTime, size",
                    )
                    .execute()
                )
                logger.info(f"Updated file on Drive: ID={self.file_id}")
                return self.file_id
            else:
                # Attempt to create new file
                file_metadata: Dict[str, Any] = {
                    "name": self.file_name,
                    "mimeType": EXCEL_MIMETYPE,
                }
                if self.folder_id:
                    file_metadata["parents"] = [self.folder_id]

                try:
                    created_file = (
                        self.service.files()
                        .create(
                            body=file_metadata,
                            media_body=media,
                            fields="id, name, modifiedTime",
                        )
                        .execute()
                    )
                    self.file_id = created_file.get("id")
                    logger.info(f"Created new file on Drive: ID={self.file_id}")
                    return self.file_id
                except Exception as create_err:
                    err_str = str(create_err)
                    if "storageQuotaExceeded" in err_str or "storage quota" in err_str:
                        self.status_message = (
                            "Google Drive Notice: Service accounts have 0MB personal quota. "
                            "Please upload the file 'personal_notes.xlsx' once into your 'Farm Notes Database' folder on Drive. "
                            "The app will then edit and sync it automatically."
                        )
                        logger.warning(self.status_message)
                    else:
                        logger.error(f"Failed to create file on Drive: {create_err}")
                    return None

        except Exception as e:
            logger.error(f"Failed to upload {self.file_name} to Drive: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """Returns the current connection and file status for UI display."""
        return {
            "is_connected": self.is_connected,
            "status_message": self.status_message,
            "file_id": self.file_id,
            "file_name": self.file_name,
            "folder_id": self.folder_id,
            "service_account_path": self.service_account_path,
        }
