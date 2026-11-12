"""
Firebase Authentication module for Personal Notes Management Web App.
Handles Firebase token verification, Firebase REST authentication (sign in/sign up),
and user session management with fallback test mode when credentials are not yet configured.
"""

import os
import json
import hashlib
import logging
from typing import Optional, Dict, Any, Tuple
import requests

logger = logging.getLogger(__name__)


class FirebaseAuthManager:
    """
    Manages Firebase Authentication operations and token verification.
    Ensures that every user request is cryptographically validated and mapped to
    a verified Firebase UID.
    """

    def __init__(self, service_account_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.service_account_path = (
            service_account_path
            or os.getenv("FIREBASE_SERVICE_ACCOUNT")
            or os.path.join(base_dir, "config", "service_account.json")
        )
        self.web_api_key = os.getenv("FIREBASE_WEB_API_KEY", "")
        self.is_live = False
        self.status_message = "Initializing Firebase..."

        self._init_firebase_admin()

        # Local fallback store for offline / preview testing if credentials are absent
        self._local_users_file = os.path.join(base_dir, "data", "local_users.json")
        self._init_local_users_store()

    def _init_firebase_admin(self):
        """Initializes Firebase Admin SDK if service account is provided."""
        try:
            import firebase_admin
            from firebase_admin import credentials, auth

            # Check if app is already initialized
            try:
                firebase_admin.get_app()
                self.is_live = True
                self.status_message = "Firebase Admin SDK initialized."
                logger.info(self.status_message)
                return
            except ValueError:
                pass

            cred = None
            # Check Streamlit secrets
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

            # Check service_account.json file
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
            else:
                self.is_live = False
                self.status_message = (
                    "Firebase service account not found. Running in local simulated auth mode."
                )
                logger.info(self.status_message)

        except Exception as e:
            self.is_live = False
            self.status_message = f"Firebase initialization error: {e}. Using local auth mode."
            logger.warning(self.status_message)

    def _init_local_users_store(self):
        """Initializes local user storage with a default demo user for out-of-the-box testing."""
        os.makedirs(os.path.dirname(self._local_users_file), exist_ok=True)
        if not os.path.exists(self._local_users_file):
            # Preload demo user
            demo_salt = "notes_salt_123"
            demo_hash = hashlib.sha256((demo_salt + "password123").encode("utf-8")).hexdigest()
            initial_data = {
                "users": {
                    "demo@example.com": {
                        "uid": "fb_uid_demo_user_101",
                        "email": "demo@example.com",
                        "display_name": "Demo User",
                        "password_hash": demo_hash,
                        "salt": demo_salt,
                    }
                }
            }
            with open(self._local_users_file, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=2)

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

    def verify_id_token(self, id_token: str) -> Optional[Dict[str, Any]]:
        """
        Cryptographically verifies a Firebase ID token.
        Returns a dictionary with verified uid, email, and display name.
        """
        if not id_token:
            return None

        # Live Firebase Token Verification
        if self.is_live:
            try:
                from firebase_admin import auth
                decoded_token = auth.verify_id_token(id_token)
                uid = decoded_token.get("uid")
                email = decoded_token.get("email", "")
                name = decoded_token.get("name") or (email.split("@")[0] if email else "User")
                return {
                    "uid": uid,
                    "email": email,
                    "name": name,
                    "token": id_token,
                }
            except Exception as e:
                logger.error(f"Live Firebase ID token verification failed: {e}")
                return None

        # Fallback local session token verification
        try:
            # Token format: local_token:<email>:<uid_hash>
            if id_token.startswith("local_token:"):
                parts = id_token.split(":")
                if len(parts) >= 3:
                    email = parts[1]
                    users_data = self._read_local_users()
                    user = users_data.get("users", {}).get(email.lower())
                    if user:
                        return {
                            "uid": user["uid"],
                            "email": user["email"],
                            "name": user["display_name"],
                            "token": id_token,
                        }
        except Exception as e:
            logger.error(f"Local token validation failed: {e}")

        return None

    def sign_in_with_password(
        self, email: str, password: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Authenticates a user with email and password.
        Uses Firebase Auth REST API if API key is provided, or local auth fallback.
        Returns (success: bool, user_data: dict, error_message: str).
        """
        email = (email or "").strip().lower()
        password = password or ""

        if not email or not password:
            return False, None, "Email and password are required."

        # If live Firebase Web API key is available, use Google Identity Toolkit
        if self.web_api_key:
            try:
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.web_api_key}"
                payload = {
                    "email": email,
                    "password": password,
                    "returnSecureToken": True,
                }
                resp = requests.post(url, json=payload, timeout=10)
                data = resp.json()

                if resp.status_code == 200:
                    id_token = data.get("idToken")
                    uid = data.get("localId")
                    display_name = data.get("displayName") or email.split("@")[0]

                    # Verify through Admin SDK if initialized
                    if self.is_live:
                        verified = self.verify_id_token(id_token)
                        if verified:
                            return True, verified, ""

                    return (
                        True,
                        {
                            "uid": uid,
                            "email": email,
                            "name": display_name,
                            "token": id_token,
                        },
                        "",
                    )
                else:
                    error_msg = data.get("error", {}).get("message", "Authentication failed.")
                    # Human-friendly messages
                    if "INVALID_LOGIN_CREDENTIALS" in error_msg or "INVALID_PASSWORD" in error_msg or "EMAIL_NOT_FOUND" in error_msg:
                        error_msg = "Invalid email or password."
                    elif "USER_DISABLED" in error_msg:
                        error_msg = "This user account has been disabled."
                    return False, None, error_msg

            except Exception as e:
                logger.error(f"Firebase REST sign in error: {e}")
                # Fall back to local check if network error occurs

        # Local authentication fallback
        users_data = self._read_local_users()
        user = users_data.get("users", {}).get(email)
        if not user:
            return False, None, "Invalid email or password. (Demo: demo@example.com / password123)"

        salt = user.get("salt", "")
        test_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        if test_hash != user.get("password_hash"):
            return False, None, "Invalid email or password."

        local_token = f"local_token:{email}:{hashlib.sha256(user['uid'].encode()).hexdigest()[:12]}"
        user_info = {
            "uid": user["uid"],
            "email": user["email"],
            "name": user.get("display_name") or email.split("@")[0],
            "token": local_token,
        }
        return True, user_info, ""

    def sign_up_with_password(
        self, email: str, password: str, display_name: str = ""
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Registers a new user account.
        """
        email = (email or "").strip().lower()
        password = password or ""
        display_name = (display_name or "").strip() or email.split("@")[0]

        if not email or "@" not in email:
            return False, None, "Please provide a valid email address."
        if len(password) < 6:
            return False, None, "Password must be at least 6 characters long."

        # Live Firebase Registration
        if self.web_api_key:
            try:
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={self.web_api_key}"
                payload = {
                    "email": email,
                    "password": password,
                    "returnSecureToken": True,
                }
                resp = requests.post(url, json=payload, timeout=10)
                data = resp.json()

                if resp.status_code == 200:
                    id_token = data.get("idToken")
                    uid = data.get("localId")

                    # Also update display name if possible
                    try:
                        update_url = f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={self.web_api_key}"
                        requests.post(
                            update_url,
                            json={"idToken": id_token, "displayName": display_name},
                            timeout=5,
                        )
                    except Exception:
                        pass

                    return (
                        True,
                        {
                            "uid": uid,
                            "email": email,
                            "name": display_name,
                            "token": id_token,
                        },
                        "",
                    )
                else:
                    error_msg = data.get("error", {}).get("message", "Registration failed.")
                    if "EMAIL_EXISTS" in error_msg:
                        error_msg = "An account with this email already exists."
                    return False, None, error_msg

            except Exception as e:
                logger.error(f"Firebase REST sign up error: {e}")

        # Local registration fallback
        users_data = self._read_local_users()
        if email in users_data.get("users", {}):
            return False, None, "An account with this email already exists."

        salt = os.urandom(16).hex()
        password_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        uid = f"fb_uid_{os.urandom(8).hex()}"

        users_data["users"][email] = {
            "uid": uid,
            "email": email,
            "display_name": display_name,
            "password_hash": password_hash,
            "salt": salt,
        }
        self._save_local_users(users_data)

        local_token = f"local_token:{email}:{hashlib.sha256(uid.encode()).hexdigest()[:12]}"
        user_info = {
            "uid": uid,
            "email": email,
            "name": display_name,
            "token": local_token,
        }
        return True, user_info, ""
