# Personal User Notes Management Web App

A modern, responsive, secure web application built with **Python Streamlit** as the backend, **Firebase Authentication** for user access control, an **Excel workbook (.xlsx) stored on Google Drive** for data persistence, and a custom **HTML/CSS/JavaScript** frontend seamlessly embedded via Streamlit custom components.

---

## 🌟 Key Features

1. **Modern Responsive Frontend (`index.html`, `style.css`, `script.js`):**
   - Clean, executive design inspired by modern productivity tools.
   - Minimalist dashboard with Inter typography, rounded cards, and smooth micro-interactions.
   - Mobile and desktop responsive layouts.
   - Interactive modals for note creation and editing with character counting.
   - Delete confirmation dialog with note snippet preview.
   - Toast notification alerts for user feedback.
   - Instant search and dual-filter toolbar (by Category and Priority).
   - Quick statistics cards (Total Notes, Work, Personal, High Priority).

2. **Secure Authentication (Firebase Authentication):**
   - Email/password authentication and account registration.
   - Server-side cryptographic Firebase ID token verification.
   - Strict isolation: Each user only accesses notes linked to their verified Firebase UID.
   - Defense in depth: The backend never trusts client-supplied user UIDs.
   - Local authentication simulation mode for immediate evaluation without setup.

3. **Google Drive & Excel Database (`google_drive.py`, `excel_manager.py`):**
   - Central Excel workbook (`personal_notes.xlsx`) stored in Google Drive.
   - Thread-safe and process-safe concurrency protection via `filelock.FileLock` and `threading.RLock`.
   - Prevents race conditions and overwrites during simultaneous user access.
   - Automatically synchronizes local changes with Google Drive API v3.
   - Strict row-level security: read, update, and delete operations enforce `User UID == authenticated_uid`.

4. **Seamless Streamlit Integration (`app.py`):**
   - Full-width, full-height custom component embedding.
   - Bidirectional communication protocol between JavaScript and Streamlit backend.
   - Eliminates standard Streamlit chrome margins for a pure web app appearance.

---

## 📁 Project Structure

```text
personal_notes_app/
│
├── app.py                      # Main Streamlit backend & component bridge
├── firebase_auth.py            # Firebase Auth & token verification manager
├── google_drive.py             # Google Drive API client (search, download, upload)
├── excel_manager.py            # Thread-safe Excel database & user UID isolation
├── requirements.txt            # Python package dependencies
├── .env.example                # Environment variables template
│
├── frontend/
│   ├── index.html              # Frontend UI structure & modals
│   ├── style.css               # Modern typography, responsive cards & themes
│   └── script.js               # Component messaging, state & filtering logic
│
├── config/
│   └── service_account.json    # Google Cloud / Firebase service account key
│
└── README.md                   # Complete documentation & setup guide
```

---

## 📊 Excel Database Schema

The central workbook contains the following columns:

| Column Name | Data Type | Description |
|---|---|---|
| `Note ID` | String | Unique note identifier (e.g. `note_744a467986`) |
| `User UID` | String | Verified Firebase UID of the note owner |
| `Username` | String | Display name of the user |
| `Selection 1` | String | Category (Work, Personal, Ideas, Meetings, Projects, Urgent, Study) |
| `Selection 2` | String | Priority (Critical, High, Medium, Low) |
| `Note Content` | Text | Full text body of the note |
| `Created Date` | Timestamp | `YYYY-MM-DD HH:MM:SS` |
| `Updated Date` | Timestamp | `YYYY-MM-DD HH:MM:SS` |

---

## 🚀 Quick Start (Out-of-the-Box Mode)

The application includes an **intelligent fallback mode**: you can run and test it **immediately**, even before configuring Google Cloud or Firebase!

### 1. Clone or Navigate to the Project
```bash
cd personal_notes_app
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Launch the Application
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

### 4. Test Demo Credentials
- Click **"⚡ Fill Demo Account"** or enter:
  - **Email:** `demo@example.com`
  - **Password:** `password123`
- Or click the **"Create Account"** tab to register any new test user!

---

## 🔑 Cloud Integration Setup

To connect the application to **Live Google Drive** and **Live Firebase**, follow these steps:

### Part A: Google Drive API Setup

1. **Create a Google Cloud Project:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Click **Select a Project** > **New Project** and name it (e.g., `Personal-Notes-App`).

2. **Enable Google Drive API:**
   - In the Google Cloud Console, navigate to **APIs & Services** > **Library**.
   - Search for **Google Drive API** and click **Enable**.

3. **Create a Service Account:**
   - Go to **APIs & Services** > **Credentials**.
   - Click **Create Credentials** > **Service Account**.
   - Name it (e.g. `notes-drive-service-account`).
   - Grant the role **Editor** or **Drive Admin** (or basic **Editor** role).
   - Click **Done**.

4. **Generate and Download JSON Key:**
   - Click on the created service account email.
   - Go to the **Keys** tab > **Add Key** > **Create new key**.
   - Select **JSON** and click **Create**.
   - Save the downloaded file as `config/service_account.json` in `personal_notes_app/`.

5. *(Optional)* **Use a Specific Google Drive Folder:**
   - In your personal Google Drive, create a folder named `Notes Database`.
   - Click **Share** on that folder and paste your Service Account's email address (`...@...iam.gserviceaccount.com`) as an **Editor**.
   - Copy the Folder ID from the URL (`https://drive.google.com/drive/folders/<FOLDER_ID>`).
   - Set `GOOGLE_DRIVE_FOLDER_ID=<FOLDER_ID>` in your `.env` or Streamlit secrets.

---

### Part B: Firebase Authentication Setup

1. **Create Firebase Project:**
   - Open the [Firebase Console](https://console.firebase.google.com/).
   - Click **Add project** and link it to your Google Cloud project (or create a new Firebase project).

2. **Enable Email/Password Sign-In:**
   - In the left sidebar, click **Build** > **Authentication**.
   - Click **Get Started**, then select **Sign-in method**.
   - Enable **Email/Password** and click **Save**.

3. **Get Firebase Web API Key:**
   - Go to **Project Settings** (gear icon in the top left).
   - In the **General** tab, under "Your project", look for **Web API Key**.
   - Set this key in your `.env` file:
     ```env
     FIREBASE_WEB_API_KEY=AIzaSy...
     ```

4. **Service Account for Admin SDK:**
   - In Firebase Console > **Project Settings** > **Service accounts** tab.
   - Click **Generate new private key**.
   - You can use this key as `config/service_account.json`. (A single GCP/Firebase service account can serve both Firebase Admin and Google Drive APIs).

---

## ⚙️ Configuration Methods

You can provide credentials using either `.env` or `st.secrets`:

### Option 1: `.env` file (Local Development)
Create a `.env` file in `personal_notes_app/` (copy from `.env.example`):
```env
GOOGLE_APPLICATION_CREDENTIALS=config/service_account.json
GOOGLE_DRIVE_FOLDER_ID=your_optional_folder_id
FIREBASE_WEB_API_KEY=your_firebase_web_api_key
FIREBASE_SERVICE_ACCOUNT=config/service_account.json
```

### Option 2: Streamlit Secrets (`.streamlit/secrets.toml`) (Cloud Deployment)
```toml
FIREBASE_WEB_API_KEY = "your_firebase_web_api_key"
GOOGLE_DRIVE_FOLDER_ID = "your_optional_folder_id"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

---

## 🔒 Security & Concurrency Design

- **Zero-Trust User Identifier:**
  The frontend never dictates user ownership. When a note is created, updated, or deleted, the backend reads the UID directly from the verified session state (`st.session_state.user["uid"]`).
- **Cryptographic Token Verification:**
  Firebase ID tokens are verified using `firebase_admin.auth.verify_id_token()`.
- **Row-Level Access Enforcement:**
  `ExcelNotesManager.get_notes_for_user()` applies strict boolean masking `df["User UID"] == user_uid`. Notes belonging to other users are never serialized or transmitted.
- **Permission Validation:**
  `update_note` and `delete_note` verify that the target note's `User UID` matches the session UID before any write is executed. If a tampering attempt occurs, a `PermissionError` is raised and logged.
- **Concurrent File Locking:**
  File access is wrapped with `filelock.FileLock(timeout=15)` and `threading.RLock()`. Every write operation downloads the latest remote revision, applies modifications, writes locally, and uploads atomically back to Google Drive before releasing the lock.

---

## 🧪 Testing Verification

You can run automated self-tests with:
```bash
python -c "
import sys
sys.path.append('personal_notes_app')
from firebase_auth import FirebaseAuthManager
from excel_manager import ExcelNotesManager

auth = FirebaseAuthManager()
ok, user, _ = auth.sign_in_with_password('demo@example.com', 'password123')
assert ok, 'Demo login failed'

excel = ExcelNotesManager()
n = excel.add_note(user['uid'], user['name'], 'Work', 'High', 'Test note')
notes = excel.get_notes_for_user(user['uid'])
assert any(x['note_id'] == n['note_id'] for x in notes)
excel.delete_note(n['note_id'], user['uid'])
print('All automated tests passed!')
"
```

