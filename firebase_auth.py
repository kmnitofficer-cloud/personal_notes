"""
Firebase Authentication module for Personal Notes Management Web App.
Handles username/password login, Firebase token verification, and user profiles
with Zone assignments for Chilaw, Puttalam, and Middle Zone.
"""

import os
import json
import time
import hmac
import hashlib
import logging
from typing import Optional, Dict, Any, Tuple
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

SESSION_SECRET = os.getenv("SESSION_SECRET", "farmnotes_auth_secret_salt_2026_fieldnotes")

# Predefined Officer Users and Zones
OFFICERS = {
    "vishmika": {
        "uid": "fb_uid_vishmika_chilaw",
        "username": "vishmika",
        "email": "vishmika@farmnotes.internal",
        "display_name": "Mr. Vishmika",
        "zone": "Chilaw",
    },
    "janaka": {
        "uid": "fb_uid_janaka_puttalam",
        "username": "janaka",
        "email": "janaka@farmnotes.internal",
        "display_name": "Mr. Janaka",
        "zone": "Puttalam",
    },
    "shashika": {
        "uid": "fb_uid_shashika_puttalam",
        "username": "shashika",
        "email": "shashika@farmnotes.internal",
        "display_name": "Mr. Shashika",
        "zone": "Puttalam",
    },
    "ashen": {
        "uid": "fb_uid_ashen_middlezone",
        "username": "ashen",
        "email": "ashen@farmnotes.internal",
        "display_name": "Mr. Ashen",
        "zone": "Middle Zone",
    },
    "janushan": {
        "uid": "fb_uid_janushan_middlezone",
        "username": "janushan",
        "email": "janushan@farmnotes.internal",
        "display_name": "Mr. Janushan",
        "zone": "Middle Zone",
    },
}


class FirebaseAuthManager:
    """
    Manages Firebase Authentication operations, username-based login,
    and user session management with Zone assignments.
    """

    def __init__(self, service_account_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.service_account_path = (
            service_account_path
            or os.getenv("FIREBASE_SERVICE_ACCOUNT")
            or os.path.join(base_dir, "config", "service_account.json")
        )
        # Check Streamlit secrets first for Web API Key
        secret_api_key = None
        try:
            import streamlit as st
            if hasattr(st, "secrets") and "FIREBASE_WEB_API_KEY" in st.secrets:
                secret_api_key = str(st.secrets["FIREBASE_WEB_API_KEY"]).strip()
        except Exception:
            pass

        self.web_api_key = secret_api_key or os.getenv("FIREBASE_WEB_API_KEY", "")
        self.is_live = False
        self.status_message = "Initializing Firebase..."

        self._init_firebase_admin()

        # Local user store
        self._local_users_file = os.path.join(base_dir, "data", "local_users.json")
        self._init_local_users_store()

    def _init_firebase_admin(self):
        """Initializes Firebase Admin SDK if service account is provided."""
        try:
            import firebase_admin
            from firebase_admin import credentials, auth

            try:
                firebase_admin.get_app()
                self.is_live = True
                self.status_message = "Firebase Admin SDK initialized."
                logger.info(self.status_message)
                return
            except ValueError:
                pass

            cred = None
            try:
                import streamlit as st
                if hasattr(st, "secrets"):
                    if "firebase_service_account" in st.secrets:
                        cred_dict = dict(st.secrets["firebase_service_account"])
                        cred = credentials.Certificate(cred_dict)
                    elif "gcp_service_account" in st.secrets:
                        cred_dict = dict(st.secrets["gcp_service_account"])
                        cred = credentials.Certificate(cred_dict)
                    if "FIREBASE_WEB_API_KEY" in st.secrets:
                        self.web_api_key = st.secrets["FIREBASE_WEB_API_KEY"]
            except Exception:
                pass

            if cred is None and os.path.exists(self.service_account_path):
                try:
                    with open(self.service_account_path, "r", encoding="utf-8") as f:
                        account_data = json.load(f)
                    pk = account_data.get("private_key", "")
                    if "YOUR_PRIVATE_KEY_HERE" in pk or len(pk) < 100:
                        self.status_message = "Template service_account.json detected. Local auth mode active."
                    else:
                        cred = credentials.Certificate(account_data)
                except Exception as e:
                    logger.info(f"service_account.json not loaded: {e}")

            if cred:
                firebase_admin.initialize_app(cred)
                self.is_live = True
                self.status_message = "Firebase Admin SDK connected and ready."
                logger.info(self.status_message)
            elif self.web_api_key:
                self.is_live = True
                self.status_message = "Firebase Authentication API connected and active."
                logger.info(self.status_message)
            else:
                self.is_live = False
                self.status_message = (
                    "Firebase service account not found. Running in local simulated auth mode."
                )
                logger.info(self.status_message)

        except Exception as e:
            self.is_live = False
            self.status_message = f"Firebase initialization: {e}. Using local auth mode."
            logger.warning(self.status_message)

    def _init_local_users_store(self):
        """Initializes local user storage with the specified officer users."""
        os.makedirs(os.path.dirname(self._local_users_file), exist_ok=True)
        users_data = {}
        if os.path.exists(self._local_users_file):
            try:
                with open(self._local_users_file, "r", encoding="utf-8") as f:
                    users_data = json.load(f)
            except Exception:
                users_data = {}

        if "users" not in users_data:
            users_data["users"] = {}

        # Ensure all predefined officer accounts exist with default password 'password123'
        default_salt = "farm_notes_salt_2026"
        default_hash = hashlib.sha256((default_salt + "password123").encode("utf-8")).hexdigest()

        for uname, info in OFFICERS.items():
            if uname not in users_data["users"]:
                users_data["users"][uname] = {
                    "uid": info["uid"],
                    "username": info["username"],
                    "email": info["email"],
                    "display_name": info["display_name"],
                    "zone": info["zone"],
                    "password_hash": default_hash,
                    "salt": default_salt,
                }
            else:
                # Update zone and display_name if needed
                users_data["users"][uname]["zone"] = info["zone"]
                users_data["users"][uname]["display_name"] = info["display_name"]

        # Also support demo user for backwards compatibility
        if "demo@example.com" not in users_data["users"]:
            users_data["users"]["demo@example.com"] = {
                "uid": "fb_uid_demo_user_101",
                "username": "demo",
                "email": "demo@example.com",
                "display_name": "Demo User",
                "zone": "All Zones",
                "password_hash": default_hash,
                "salt": default_salt,
            }

        with open(self._local_users_file, "w", encoding="utf-8") as f:
            json.dump(users_data, f, indent=2)

    def _read_local_users(self) -> Dict[str, Any]:
        """Reads local users database file."""
        try:
            with open(self._local_users_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"users": {}}

    def _save_local_users(self, data: Dict[str, Any]):
        """Saves local users database file."""
        with open(self._local_users_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def normalize_username(self, identifier: str) -> str:
        """Normalizes username or email input."""
        raw = (identifier or "").strip().lower()
        # Remove common prefixes like 'mr.'
        if raw.startswith("mr."):
            raw = raw[3:].strip()
        elif raw.startswith("mr "):
            raw = raw[3:].strip()
        return raw

    def get_firebase_email(self, username: str) -> str:
        """Translates a username into an email string required by Firebase Auth."""
        norm = self.normalize_username(username)
        if "@" in norm:
            return norm
        return f"{norm}@farmnotes.internal"

    def create_session_token(
        self, uid: str, username: str, zone: str = "", display_name: str = "", days: int = 30
    ) -> str:
        """
        Creates a tamper-proof HMAC-SHA256 signed session token valid for `days` days.
        Guarantees persistent login across browser refreshes and mobile PWA shortcuts.
        """
        expiry = int(time.time()) + (days * 86400)
        clean_uid = str(uid).strip()
        clean_uname = self.normalize_username(username)
        clean_zone = str(zone or "Chilaw").strip()
        clean_name = str(display_name or clean_uname.capitalize()).strip()
        data = f"{clean_uid}|{clean_uname}|{clean_zone}|{clean_name}|{expiry}"
        sig = hmac.new(
            SESSION_SECRET.encode("utf-8"), data.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"sess:{clean_uid}:{clean_uname}:{clean_zone}:{clean_name}:{expiry}:{sig}"

    def verify_session_token(self, token_str: str) -> Optional[Dict[str, Any]]:
        """
        Validates a tamper-proof session token.
        Returns user info dictionary if valid and unexpired, else None.
        """
        if not token_str or not token_str.startswith("sess:"):
            return None
        try:
            parts = token_str.split(":")
            if len(parts) != 7:
                return None
            _, uid, username, zone, display_name, expiry_str, sig = parts
            expiry = int(expiry_str)
            if time.time() > expiry:
                logger.info(f"Session token for {username} expired.")
                return None

            data = f"{uid}|{username}|{zone}|{display_name}|{expiry}"
            expected_sig = hmac.new(
                SESSION_SECRET.encode("utf-8"), data.encode("utf-8"), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(sig, expected_sig):
                logger.warning(f"Signature mismatch on session token for {username}.")
                return None

            return {
                "uid": uid,
                "username": username,
                "email": self.get_firebase_email(username),
                "name": display_name or username.capitalize(),
                "zone": zone or "Chilaw",
                "token": token_str,
            }
        except Exception as e:
            logger.error(f"Error parsing session token: {e}")
            return None

    def verify_id_token(self, id_token: str) -> Optional[Dict[str, Any]]:
        """
        Verifies authentication tokens:
        1. 30-day HMAC persistent session tokens (sess:...)
        2. Firebase REST API accounts:lookup
        3. Live Firebase Admin SDK
        4. Local offline token fallback
        """
        if not id_token:
            return None

        # 1. Check persistent session token (sess:...)
        if id_token.startswith("sess:"):
            sess_user = self.verify_session_token(id_token)
            if sess_user:
                return sess_user

        # 2. REST API verification using Google Identity Toolkit (accounts:lookup)
        if self.web_api_key and id_token.startswith("eyJ"):
            try:
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={self.web_api_key}"
                resp = requests.post(url, json={"idToken": id_token}, timeout=6)
                if resp.status_code == 200:
                    data = resp.json()
                    users = data.get("users", [])
                    if users:
                        user_info = users[0]
                        uid = user_info.get("localId")
                        email = user_info.get("email", "")
                        username = email.split("@")[0]

                        zone = "Chilaw"
                        display_name = username.capitalize()
                        for o_uname, o_info in OFFICERS.items():
                            if o_uname == username or o_info["uid"] == uid:
                                zone = o_info["zone"]
                                display_name = o_info["display_name"]
                                break

                        fresh_session = self.create_session_token(
                            uid=uid, username=username, zone=zone, display_name=display_name, days=30
                        )
                        return {
                            "uid": uid,
                            "username": username,
                            "email": email,
                            "name": display_name,
                            "zone": zone,
                            "token": fresh_session,
                        }
            except Exception as e:
                logger.warning(f"REST API account lookup failed: {e}")

        # 3. Live Firebase Token Verification via Admin SDK
        if self.is_live:
            try:
                from firebase_admin import auth
                decoded_token = auth.verify_id_token(id_token)
                uid = decoded_token.get("uid")
                email = decoded_token.get("email", "")
                username = email.split("@")[0]
                name = decoded_token.get("name") or username.capitalize()

                zone = "Chilaw"
                for o_uname, o_info in OFFICERS.items():
                    if o_info["uid"] == uid or o_uname == username:
                        zone = o_info["zone"]
                        name = o_info["display_name"]
                        break

                fresh_session = self.create_session_token(
                    uid=uid, username=username, zone=zone, display_name=name, days=30
                )
                return {
                    "uid": uid,
                    "username": username,
                    "email": email,
                    "name": name,
                    "zone": zone,
                    "token": fresh_session,
                }
            except Exception as e:
                logger.debug(f"Firebase Admin SDK token verification skipped: {e}")

        # 4. Fallback local token verification
        try:
            if id_token.startswith("local_token:"):
                parts = id_token.split(":")
                if len(parts) >= 3:
                    uname = parts[1]
                    users_data = self._read_local_users()
                    user = users_data.get("users", {}).get(uname.lower())
                    if user:
                        fresh_session = self.create_session_token(
                            uid=user["uid"],
                            username=user.get("username", uname),
                            zone=user.get("zone", "Chilaw"),
                            display_name=user["display_name"],
                            days=30,
                        )
                        return {
                            "uid": user["uid"],
                            "username": user.get("username", uname),
                            "email": user["email"],
                            "name": user["display_name"],
                            "zone": user.get("zone", "Chilaw"),
                            "token": fresh_session,
                        }
        except Exception as e:
            logger.error(f"Local token validation failed: {e}")

        return None

    def sign_in_with_username_or_email(
        self, username_or_email: str, password: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Authenticates a user with username (or email) and password.
        Uses Firebase Auth REST API if API key is provided, or local auth fallback.
        Generates a 30-day persistent session token for mobile web apps.
        """
        raw_input = (username_or_email or "").strip()
        norm_key = self.normalize_username(raw_input)
        password = password or ""

        if not norm_key or not password:
            return False, None, "Username and password are required."

        # If live Firebase Web API key is available, use Google Identity Toolkit
        if self.web_api_key:
            try:
                firebase_email = self.get_firebase_email(norm_key)
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.web_api_key}"
                payload = {
                    "email": firebase_email,
                    "password": password,
                    "returnSecureToken": True,
                }
                resp = requests.post(url, json=payload, timeout=10)
                data = resp.json()

                if resp.status_code == 200:
                    id_token = data.get("idToken")
                    uid = data.get("localId")

                    # Look up zone
                    zone = "Chilaw"
                    display_name = norm_key.capitalize()
                    for o_uname, o_info in OFFICERS.items():
                        if o_uname == norm_key:
                            zone = o_info["zone"]
                            display_name = o_info["display_name"]
                            break

                    session_token = self.create_session_token(
                        uid=uid, username=norm_key, zone=zone, display_name=display_name, days=30
                    )

                    return (
                        True,
                        {
                            "uid": uid,
                            "username": norm_key,
                            "email": firebase_email,
                            "name": display_name,
                            "zone": zone,
                            "token": session_token,
                            "firebase_id_token": id_token,
                        },
                        "",
                    )
                else:
                    error_msg = data.get("error", {}).get("message", "Authentication failed.")
                    if "INVALID_LOGIN_CREDENTIALS" in error_msg or "INVALID_PASSWORD" in error_msg or "EMAIL_NOT_FOUND" in error_msg:
                        error_msg = "Invalid username or password."
                    return False, None, error_msg

            except Exception as e:
                logger.error(f"Firebase REST sign in error: {e}")

        # Local authentication fallback
        users_data = self._read_local_users()
        user_entry = None
        # Try direct match, or email match, or officer key
        users_dict = users_data.get("users", {})
        if norm_key in users_dict:
            user_entry = users_dict[norm_key]
        else:
            for k, u in users_dict.items():
                if u.get("email", "").lower() == norm_key.lower() or u.get("username", "").lower() == norm_key.lower():
                    user_entry = u
                    break

        if not user_entry:
            return False, None, "Invalid username or password. Check officer names or default password123."

        salt = user_entry.get("salt", "")
        test_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        if test_hash != user_entry.get("password_hash"):
            return False, None, "Invalid username or password."

        session_token = self.create_session_token(
            uid=user_entry["uid"],
            username=user_entry.get("username", norm_key),
            zone=user_entry.get("zone", "Chilaw"),
            display_name=user_entry.get("display_name", norm_key.capitalize()),
            days=30,
        )
        user_info = {
            "uid": user_entry["uid"],
            "username": user_entry.get("username", norm_key),
            "email": user_entry.get("email", f"{norm_key}@farmnotes.internal"),
            "name": user_entry.get("display_name", norm_key.capitalize()),
            "zone": user_entry.get("zone", "Chilaw"),
            "token": session_token,
        }
        return True, user_info, ""

    def sign_up_user(
        self, username: str, password: str, display_name: str = "", zone: str = "Chilaw"
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Registers a new officer or user account with an assigned Zone.
        """
        username = self.normalize_username(username)
        password = password or ""
        display_name = (display_name or "").strip() or username.capitalize()
        zone = (zone or "Chilaw").strip()

        if not username or len(username) < 3:
            return False, None, "Username must be at least 3 characters long."
        if len(password) < 6:
            return False, None, "Password must be at least 6 characters long."

        firebase_email = self.get_firebase_email(username)

        # Live Firebase Registration
        if self.web_api_key:
            try:
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={self.web_api_key}"
                payload = {
                    "email": firebase_email,
                    "password": password,
                    "returnSecureToken": True,
                }
                resp = requests.post(url, json=payload, timeout=10)
                data = resp.json()

                if resp.status_code == 200:
                    id_token = data.get("idToken")
                    uid = data.get("localId")
                    return (
                        True,
                        {
                            "uid": uid,
                            "username": username,
                            "email": firebase_email,
                            "name": display_name,
                            "zone": zone,
                            "token": id_token,
                        },
                        "",
                    )
            except Exception as e:
                logger.error(f"Firebase REST sign up error: {e}")

        # Local registration fallback
        users_data = self._read_local_users()
        if username in users_data.get("users", {}):
            return False, None, "An account with this username already exists."

        salt = os.urandom(16).hex()
        password_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        uid = f"fb_uid_{username}_{os.urandom(4).hex()}"

        users_data["users"][username] = {
            "uid": uid,
            "username": username,
            "email": firebase_email,
            "display_name": display_name,
            "zone": zone,
            "password_hash": password_hash,
            "salt": salt,
        }
        self._save_local_users(users_data)

        local_token = f"local_token:{username}:{hashlib.sha256(uid.encode()).hexdigest()[:12]}"
        user_info = {
            "uid": uid,
            "username": username,
            "email": firebase_email,
            "name": display_name,
            "zone": zone,
            "token": local_token,
        }
        return True, user_info, ""
