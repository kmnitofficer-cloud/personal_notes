"""
Personal User Notes Management Web App - Streamlit Backend
Combines Python Streamlit with embedded HTML/CSS/JavaScript frontend,
Firebase Authentication (username/password login), Excel database sync with Google Drive,
and master data from Running List.xlsx filtered by user Zone.
"""

import os
import sys
import time
import logging
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

# Load environment variables if present
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("personal_notes_app")

# Ensure local modules can be imported directly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from firebase_auth import FirebaseAuthManager
from google_drive import GoogleDriveManager
from excel_manager import ExcelNotesManager
from running_list_manager import RunningListManager

# Page Configuration - Full Width
st.set_page_config(
    page_title="Personal Notes Management - Running List Hub",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Inject CSS to remove Streamlit chrome and give iframe full screen
st.markdown(
    """
    <style>
        /* Hide Streamlit default header, footer and toolbars */
        header[data-testid="stHeader"] {
            display: none !important;
        }
        footer {
            display: none !important;
        }
        #MainMenu {
            display: none !important;
        }
        div[data-testid="stToolbar"] {
            display: none !important;
        }
        div[data-testid="stDecoration"] {
            display: none !important;
        }
        div[data-testid="stStatusWidget"] {
            display: none !important;
        }
        /* Remove default margins and padding */
        .stApp {
            margin: 0 !important;
            padding: 0 !important;
            background-color: #f8fafc !important;
        }
        .block-container {
            padding: 0rem !important;
            max-width: 100% !important;
            margin: 0 !important;
        }
        /* Full-screen iframe styling */
        iframe {
            width: 100% !important;
            min-height: 100vh !important;
            border: none !important;
            display: block !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_backend_managers():
    """Initializes and caches backend managers as singletons."""
    drive_mgr = GoogleDriveManager()
    auth_mgr = FirebaseAuthManager()
    excel_mgr = ExcelNotesManager(drive_manager=drive_mgr)
    running_list_mgr = RunningListManager()
    return drive_mgr, auth_mgr, excel_mgr, running_list_mgr


drive_manager, auth_manager, excel_manager, running_list_manager = get_backend_managers()

# Initialize Streamlit Session State
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "user" not in st.session_state:
    st.session_state["user"] = None
if "notes" not in st.session_state:
    st.session_state["notes"] = []
if "toast" not in st.session_state:
    st.session_state["toast"] = None
if "error" not in st.session_state:
    st.session_state["error"] = None
if "last_processed_req_id" not in st.session_state:
    st.session_state["last_processed_req_id"] = None

# Declare Frontend Custom Component
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
notes_custom_component = components.declare_component(
    "personal_notes_component", path=FRONTEND_DIR
)


def handle_component_action(event: dict):
    """
    Processes incoming actions from the frontend UI securely on the backend.
    Enforces user isolation and cryptographic verification.
    """
    if not event or not isinstance(event, dict):
        return

    req_id = event.get("requestId")
    if not req_id or req_id == st.session_state.get("last_processed_req_id"):
        return

    st.session_state["last_processed_req_id"] = req_id
    action = event.get("action")
    payload = event.get("payload", {})

    logger.info(f"Processing backend action: {action}")

    # Action 1: User Login with Username and Password
    if action == "login":
        id_token = payload.get("idToken")
        username = payload.get("username") or payload.get("email")
        password = payload.get("password")

        if id_token:
            verified_user = auth_manager.verify_id_token(id_token)
            if verified_user:
                st.session_state["authenticated"] = True
                st.session_state["user"] = verified_user
                st.session_state["notes"] = excel_manager.get_notes_for_user(
                    verified_user["uid"]
                )
                st.session_state["toast"] = f"Welcome back, {verified_user['name']}!"
                st.session_state["error"] = None
            else:
                st.session_state["authenticated"] = False
                st.session_state["error"] = None
        else:
            ok, user_data, err_msg = auth_manager.sign_in_with_username_or_email(
                username, password
            )
            if ok and user_data:
                st.session_state["authenticated"] = True
                st.session_state["user"] = user_data
                st.session_state["notes"] = excel_manager.get_notes_for_user(
                    user_data["uid"]
                )
                st.session_state["toast"] = (
                    f"Welcome back, {user_data['name']}! ({user_data.get('zone', 'Zone')})"
                )
                st.session_state["error"] = None
            else:
                st.session_state["authenticated"] = False
                st.session_state["error"] = err_msg or "Authentication failed."

        st.rerun()

    # Action 2: User Registration (Disabled for security)
    elif action == "signup":
        st.session_state["error"] = "Public registration is disabled. Please use your assigned officer credentials."
        st.rerun()

    # Action 3: User Logout
    elif action == "logout":
        st.session_state["authenticated"] = False
        st.session_state["user"] = None
        st.session_state["notes"] = []
        st.session_state["toast"] = "Signed out successfully."
        st.session_state["error"] = None
        st.rerun()

    # Action 4: Add New Note (Instant Local Save + Background Drive Sync)
    elif action == "add_note":
        if not st.session_state.get("authenticated") or not st.session_state.get("user"):
            st.session_state["error"] = "Session expired. Please sign in again."
            st.rerun()

        user_uid = st.session_state["user"]["uid"]
        username = st.session_state["user"]["name"]
        user_zone = st.session_state["user"].get("zone", "")

        customer_name = payload.get("customer_name") or payload.get("selection1", "")
        farm_name = payload.get("farm_name") or payload.get("selection2", "")
        content = payload.get("content", "")

        try:
            excel_manager.add_note(
                user_uid=user_uid,
                username=username,
                customer_name=customer_name,
                farm_name=farm_name,
                content=content,
                zone=user_zone,
            )
            st.session_state["notes"] = excel_manager.get_notes_for_user(user_uid, force_remote_sync=False)
            st.session_state["toast"] = "Note saved & syncing to Google Drive!"
            st.session_state["error"] = None
        except Exception as e:
            logger.error(f"Error adding note: {e}", exc_info=True)
            st.session_state["error"] = f"Failed to save note: {str(e)}"

        st.rerun()

    # Action 5: Delete Note
    elif action == "delete_note":
        if not st.session_state.get("authenticated") or not st.session_state.get("user"):
            st.session_state["error"] = "Session expired. Please sign in again."
            st.rerun()

        user_uid = st.session_state["user"]["uid"]
        username = st.session_state["user"].get("name") or st.session_state["user"].get("username", "")
        note_id = payload.get("note_id")

        try:
            excel_manager.delete_note(note_id, user_uid, username=username)
            st.session_state["notes"] = excel_manager.get_notes_for_user(user_uid, force_remote_sync=False)
            st.session_state["toast"] = "Note deleted from active list & archived in backup."
            st.session_state["error"] = None
        except PermissionError as pe:
            st.session_state["error"] = str(pe)
        except Exception as e:
            logger.error(f"Error deleting note: {e}", exc_info=True)
            st.session_state["error"] = f"Failed to delete note: {str(e)}"

        st.rerun()

    # Action 6: Sync / Refresh Notes from Google Drive
    elif action == "refresh":
        if st.session_state.get("authenticated") and st.session_state.get("user"):
            user_uid = st.session_state["user"]["uid"]
            synced = excel_manager.sync_with_drive_now()
            st.session_state["notes"] = excel_manager.get_notes_for_user(user_uid, force_remote_sync=True)
            if synced:
                st.session_state["toast"] = "Synchronized with Google Drive Excel."
            else:
                st.session_state["toast"] = "Notes refreshed."
        st.rerun()


# Prepare state dictionary to send into the frontend component
toast_to_send = st.session_state.get("toast")
error_to_send = st.session_state.get("error")
toast_id = f"toast_{time.time()}_{abs(hash(toast_to_send))}" if toast_to_send else None

# Consume one-shot messages
st.session_state["toast"] = None
st.session_state["error"] = None

# Get zone-filtered customer & farm data for the current user
current_user = st.session_state.get("user")
user_zone = current_user.get("zone", "Chilaw") if current_user else "Chilaw"
zone_bundle = running_list_manager.get_zone_data_bundle(user_zone)
all_zones = running_list_manager.get_all_zones()

component_state = {
    "authenticated": st.session_state.get("authenticated", False),
    "user": current_user,
    "notes": st.session_state.get("notes", []),
    "running_list": zone_bundle,
    "all_zones": all_zones,
    "backend_status": {
        "drive": drive_manager.get_status(),
        "firebase": {
            "is_live": auth_manager.is_live,
            "status_message": auth_manager.status_message,
        },
    },
    "toast": toast_to_send,
    "toast_id": toast_id,
    "error": error_to_send,
    "timestamp": time.time(),
}

# Render frontend component inside Streamlit full-screen iframe
event_data = notes_custom_component(
    state=component_state,
    key="personal_notes_main_component",
    default=None,
)

if event_data:
    handle_component_action(event_data)
