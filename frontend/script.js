/**
 * Personal Notes Management Web App - Frontend Script
 * Interacts with Streamlit backend using Streamlit custom component postMessage protocol.
 * Handles client-side state, modal interactions, search/filtering, and responsive UI.
 */

// Application State
let appState = {
  authenticated: false,
  user: null,
  notes: [],
  backendStatus: {
    drive: { is_connected: false, status_message: "Checking..." },
    firebase: { is_live: false, status_message: "Checking..." },
  },
  filter: {
    search: "",
    category: "",
    priority: "",
  },
  activeDeleteNoteId: null,
};

// ===================================================================
// STREAMLIT COMPONENT BRIDGE
// ===================================================================

function sendToStreamlit(action, payload = {}) {
  const message = {
    isStreamlitMessage: true,
    type: "streamlit:setComponentValue",
    value: {
      action: action,
      payload: payload,
      requestId: Date.now() + "_" + Math.random().toString(36).substring(2, 9),
    },
  };
  window.parent.postMessage(message, "*");
}

function updateFrameHeight() {
  setTimeout(() => {
    const scrollH = Math.max(
      document.documentElement.scrollHeight,
      document.body.scrollHeight,
      window.innerHeight || 800
    );
    window.parent.postMessage(
      {
        isStreamlitMessage: true,
        type: "streamlit:setFrameHeight",
        height: Math.max(scrollH, 900),
      },
      "*"
    );
  }, 50);
}

// Listen for messages from Streamlit parent frame
window.addEventListener("message", (event) => {
  if (!event.data) return;

  if (event.data.type === "streamlit:render") {
    const args = event.data.args || {};
    const state = args.state || {};

    applyServerState(state);
  }
});

function applyServerState(serverState) {
  if (!serverState) return;

  appState.authenticated = !!serverState.authenticated;
  appState.user = serverState.user || null;
  appState.notes = Array.isArray(serverState.notes) ? serverState.notes : [];

  if (serverState.backend_status) {
    appState.backendStatus = serverState.backend_status;
  }

  // Handle errors
  if (serverState.error) {
    showAuthError(serverState.error);
    showToast(serverState.error, "error");
  } else {
    hideAuthError();
  }

  // Handle toasts
  if (serverState.toast) {
    showToast(serverState.toast, "success");
  }

  // Update View
  if (appState.authenticated && appState.user) {
    showDashboardView();
  } else {
    showAuthView();
  }

  updateFrameHeight();
}

// Notify Streamlit that the component is loaded
window.addEventListener("load", () => {
  window.parent.postMessage(
    {
      isStreamlitMessage: true,
      type: "streamlit:componentReady",
      apiVersion: 1,
    },
    "*"
  );
  updateFrameHeight();
  renderDate();
});

window.addEventListener("resize", updateFrameHeight);

// ===================================================================
// AUTHENTICATION LOGIC & VIEWS
// ===================================================================

function showAuthView() {
  document.getElementById("authView").style.display = "flex";
  document.getElementById("dashboardView").style.display = "none";

  // Update auth status banner
  const statusPill = document.getElementById("authStatusPill");
  const statusText = document.getElementById("authStatusText");
  const dot = statusPill.querySelector(".status-dot");

  const drive = appState.backendStatus.drive || {};
  const firebase = appState.backendStatus.firebase || {};

  if (drive.is_connected && firebase.is_live) {
    dot.className = "status-dot";
    statusText.textContent = "Google Drive API & Firebase Live";
  } else if (!drive.is_connected && !firebase.is_live) {
    dot.className = "status-dot local-mode";
    statusText.textContent = "Running in Local Storage & Auth Mode (Service Account not configured)";
  } else {
    dot.className = "status-dot local-mode";
    statusText.textContent = `Drive: ${drive.is_connected ? "Live" : "Local"} | Firebase: ${firebase.is_live ? "Live" : "Local"}`;
  }
}

function showDashboardView() {
  document.getElementById("authView").style.display = "none";
  document.getElementById("dashboardView").style.display = "block";

  // Populate user info
  const user = appState.user || { name: "User", email: "", uid: "" };
  document.getElementById("welcomeUserName").textContent = user.name || "User";
  document.getElementById("navUserName").textContent = user.name || "User";
  document.getElementById("navUserUid").textContent = `UID: ${(user.uid || "").slice(0, 16)}...`;
  document.getElementById("userAvatarText").textContent = (user.name || "U").charAt(0).toUpperCase();

  // Populate system status indicators
  const drive = appState.backendStatus.drive || {};
  const firebase = appState.backendStatus.firebase || {};

  const driveLabel = document.getElementById("driveStatusLabel");
  const drivePill = document.getElementById("driveStatusPill");
  if (drive.is_connected) {
    driveLabel.textContent = "Drive: Connected";
    drivePill.querySelector(".status-dot").className = "status-dot";
  } else {
    driveLabel.textContent = "Drive: Local Mode";
    drivePill.querySelector(".status-dot").className = "status-dot local-mode";
  }

  const authLabel = document.getElementById("authStatusLabel");
  const authPill = document.getElementById("authStatusPillDash");
  if (firebase.is_live) {
    authLabel.textContent = "Firebase: Live";
    authPill.querySelector(".status-dot").className = "status-dot";
  } else {
    authLabel.textContent = "Firebase: Local Auth";
    authPill.querySelector(".status-dot").className = "status-dot local-mode";
  }

  renderNotes();
}

function switchAuthTab(tab) {
  const tabLogin = document.getElementById("tabLogin");
  const tabRegister = document.getElementById("tabRegister");
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");

  hideAuthError();

  if (tab === "login") {
    tabLogin.classList.add("active");
    tabRegister.classList.remove("active");
    loginForm.style.display = "block";
    registerForm.style.display = "none";
  } else {
    tabLogin.classList.remove("active");
    tabRegister.classList.add("active");
    loginForm.style.display = "none";
    registerForm.style.display = "block";
  }
  updateFrameHeight();
}

function fillDemoCredentials() {
  document.getElementById("loginEmail").value = "demo@example.com";
  document.getElementById("loginPassword").value = "password123";
  showToast("Pre-filled demo credentials", "info");
}

function handleLoginSubmit(event) {
  event.preventDefault();
  hideAuthError();

  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;

  if (!email || !password) {
    showAuthError("Please enter both email and password.");
    return;
  }

  const submitBtn = document.getElementById("loginSubmitBtn");
  submitBtn.disabled = true;
  submitBtn.innerHTML = "<span>Signing in...</span>";

  sendToStreamlit("login", {
    email: email,
    password: password,
  });

  setTimeout(() => {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>Sign In to Dashboard</span>
      <svg class="btn-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="5" y1="12" x2="19" y2="12" />
        <polyline points="12 5 19 12 12 19" />
      </svg>`;
  }, 2000);
}

function handleRegisterSubmit(event) {
  event.preventDefault();
  hideAuthError();

  const name = document.getElementById("regName").value.trim();
  const email = document.getElementById("regEmail").value.trim();
  const password = document.getElementById("regPassword").value;

  if (!name || !email || !password) {
    showAuthError("Please fill in all registration fields.");
    return;
  }

  const submitBtn = document.getElementById("registerSubmitBtn");
  submitBtn.disabled = true;
  submitBtn.innerHTML = "<span>Creating account...</span>";

  sendToStreamlit("signup", {
    displayName: name,
    email: email,
    password: password,
  });

  setTimeout(() => {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>Create My Account</span>
      <svg class="btn-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="5" y1="12" x2="19" y2="12" />
        <polyline points="12 5 19 12 12 19" />
      </svg>`;
  }, 2000);
}

function handleLogout() {
  sendToStreamlit("logout", {});
}

function showAuthError(msg) {
  const alert = document.getElementById("authErrorAlert");
  const text = document.getElementById("authErrorMessage");
  text.textContent = msg;
  alert.style.display = "flex";
  updateFrameHeight();
}

function hideAuthError() {
  document.getElementById("authErrorAlert").style.display = "none";
}

// ===================================================================
// NOTES RENDERING & FILTERING
// ===================================================================

function renderNotes() {
  const grid = document.getElementById("notesGrid");
  const emptyState = document.getElementById("notesEmptyState");
  const emptyMsg = document.getElementById("emptyStateMessage");

  grid.innerHTML = "";

  const notes = appState.notes || [];

  // Filter notes based on search and dropdown filters
  const searchTerm = (appState.filter.search || "").toLowerCase().trim();
  const filterCat = appState.filter.category;
  const filterPri = appState.filter.priority;

  const filtered = notes.filter((n) => {
    const contentMatch = (n.content || "").toLowerCase().includes(searchTerm);
    const catMatch = (n.selection1 || "").toLowerCase().includes(searchTerm);
    const priMatch = (n.selection2 || "").toLowerCase().includes(searchTerm);
    const matchesSearch = !searchTerm || contentMatch || catMatch || priMatch;

    const matchesCategory = !filterCat || n.selection1 === filterCat;
    const matchesPriority = !filterPri || n.selection2 === filterPri;

    return matchesSearch && matchesCategory && matchesPriority;
  });

  // Update Stats
  updateStats(notes);

  if (filtered.length === 0) {
    emptyState.style.display = "block";
    if (notes.length > 0) {
      emptyMsg.textContent = "No notes matched your search or filter criteria.";
    } else {
      emptyMsg.textContent = "You haven't created any notes yet. Click below to add your first note!";
    }
  } else {
    emptyState.style.display = "none";
    filtered.forEach((note) => {
      grid.appendChild(createNoteCard(note));
    });
  }

  updateFrameHeight();
}

function createNoteCard(note) {
  const card = document.createElement("div");
  card.className = "note-card";
  card.id = `card-${note.note_id}`;

  const categoryClass = `tag-category-${(note.selection1 || "general").toLowerCase()}`;
  const priorityClass = `tag-priority-${(note.selection2 || "medium").toLowerCase()}`;

  const displayDate = note.updated_date || note.created_date || "Just now";

  // Sanitize text for safe HTML rendering
  const safeContent = escapeHtml(note.content || "");

  card.innerHTML = `
    <div class="card-header">
      <div class="card-badges">
        <span class="tag-badge ${categoryClass}">
          ${getCategoryIcon(note.selection1)} ${escapeHtml(note.selection1 || "General")}
        </span>
        <span class="tag-badge ${priorityClass}">
          ${escapeHtml(note.selection2 || "Medium")}
        </span>
      </div>
      <span class="card-timestamp" title="Last Updated: ${displayDate}">${formatDateSnippet(displayDate)}</span>
    </div>

    <div class="card-body">
      <p class="note-content-text">${safeContent}</p>
    </div>

    <div class="card-footer">
      <span class="note-id-pill" title="ID: ${note.note_id}">${note.note_id.slice(0, 12)}</span>
      <div class="card-actions">
        <button class="action-icon-btn" onclick="openEditNoteModal('${note.note_id}')" title="Edit note">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
        </button>
        <button class="action-icon-btn delete-btn" onclick="openDeleteModal('${note.note_id}')" title="Delete note">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </svg>
        </button>
      </div>
    </div>
  `;

  return card;
}

function updateStats(notes) {
  document.getElementById("statTotalNotes").textContent = notes.length;
  document.getElementById("statWorkNotes").textContent = notes.filter((n) => n.selection1 === "Work").length;
  document.getElementById("statPersonalNotes").textContent = notes.filter((n) => n.selection1 === "Personal").length;
  document.getElementById("statHighPriority").textContent = notes.filter(
    (n) => n.selection2 === "High" || n.selection2 === "Critical"
  ).length;
}

function handleSearchFilterChange() {
  const searchInput = document.getElementById("searchNotesInput");
  const clearBtn = document.getElementById("clearSearchBtn");
  const filterCat = document.getElementById("filterCategory").value;
  const filterPri = document.getElementById("filterPriority").value;

  appState.filter.search = searchInput.value;
  appState.filter.category = filterCat;
  appState.filter.priority = filterPri;

  clearBtn.style.display = searchInput.value ? "block" : "none";
  renderNotes();
}

function clearSearch() {
  document.getElementById("searchNotesInput").value = "";
  handleSearchFilterChange();
}

function triggerRefresh() {
  const icon = document.getElementById("refreshIcon");
  icon.classList.add("spin");
  sendToStreamlit("refresh", {});
  setTimeout(() => icon.classList.remove("spin"), 1000);
}

// ===================================================================
// ADD & EDIT NOTE MODALS
// ===================================================================

function openAddNoteModal() {
  // Use currently selected dropdown values from dashboard controls
  const dashSel1 = document.getElementById("dashboardSelect1").value;
  const dashSel2 = document.getElementById("dashboardSelect2").value;

  document.getElementById("modalTitle").textContent = "Create New Note";
  document.getElementById("modalSaveBtnText").textContent = "Save Note";
  document.getElementById("modalNoteId").value = "";
  document.getElementById("modalSelect1").value = dashSel1 || "Work";
  document.getElementById("modalSelect2").value = dashSel2 || "Medium";
  document.getElementById("modalNoteContent").value = "";
  updateCharCount();

  document.getElementById("noteModal").style.display = "flex";
  setTimeout(() => document.getElementById("modalNoteContent").focus(), 100);
}

function openEditNoteModal(noteId) {
  const note = (appState.notes || []).find((n) => n.note_id === noteId);
  if (!note) return;

  document.getElementById("modalTitle").textContent = "Edit Note";
  document.getElementById("modalSaveBtnText").textContent = "Update Note";
  document.getElementById("modalNoteId").value = note.note_id;
  document.getElementById("modalSelect1").value = note.selection1 || "Work";
  document.getElementById("modalSelect2").value = note.selection2 || "Medium";
  document.getElementById("modalNoteContent").value = note.content || "";
  updateCharCount();

  document.getElementById("noteModal").style.display = "flex";
  setTimeout(() => document.getElementById("modalNoteContent").focus(), 100);
}

function closeNoteModal() {
  document.getElementById("noteModal").style.display = "none";
}

function handleSaveNote(event) {
  event.preventDefault();

  const noteId = document.getElementById("modalNoteId").value;
  const sel1 = document.getElementById("modalSelect1").value;
  const sel2 = document.getElementById("modalSelect2").value;
  const content = document.getElementById("modalNoteContent").value.trim();

  if (!content) {
    showToast("Please enter some note content.", "error");
    return;
  }

  const saveBtn = document.getElementById("modalSaveBtn");
  saveBtn.disabled = true;

  if (noteId) {
    // Edit existing note
    sendToStreamlit("edit_note", {
      note_id: noteId,
      selection1: sel1,
      selection2: sel2,
      content: content,
    });
  } else {
    // Add new note
    sendToStreamlit("add_note", {
      selection1: sel1,
      selection2: sel2,
      content: content,
    });
  }

  closeNoteModal();
  setTimeout(() => {
    saveBtn.disabled = false;
  }, 1000);
}

function updateCharCount() {
  const content = document.getElementById("modalNoteContent").value;
  document.getElementById("charCount").textContent = `${content.length} characters`;
}

// ===================================================================
// DELETE CONFIRMATION MODAL
// ===================================================================

function openDeleteModal(noteId) {
  const note = (appState.notes || []).find((n) => n.note_id === noteId);
  if (!note) return;

  appState.activeDeleteNoteId = noteId;
  const preview = document.getElementById("deleteNotePreview");
  preview.textContent = (note.content || "").slice(0, 140) + ((note.content || "").length > 140 ? "..." : "");

  document.getElementById("deleteModal").style.display = "flex";
}

function closeDeleteModal() {
  appState.activeDeleteNoteId = null;
  document.getElementById("deleteModal").style.display = "none";
}

function confirmDeleteNote() {
  if (!appState.activeDeleteNoteId) return;

  sendToStreamlit("delete_note", {
    note_id: appState.activeDeleteNoteId,
  });

  closeDeleteModal();
}

// Close modals when clicking backdrop or pressing Escape
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeNoteModal();
    closeDeleteModal();
  }
});

document.addEventListener("click", (e) => {
  const noteModal = document.getElementById("noteModal");
  const deleteModal = document.getElementById("deleteModal");
  if (e.target === noteModal) closeNoteModal();
  if (e.target === deleteModal) closeDeleteModal();
});

// ===================================================================
// TOAST NOTIFICATIONS & UTILITIES
// ===================================================================

function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;

  let iconSvg = "";
  if (type === "success") {
    iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;
  } else if (type === "error") {
    iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
  } else {
    iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;
  }

  toast.innerHTML = `${iconSvg}<span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(20px)";
    toast.style.transition = "all 0.25s ease";
    setTimeout(() => toast.remove(), 250);
  }, 3800);
}

function renderDate() {
  const options = { weekday: "long", year: "numeric", month: "long", day: "numeric" };
  const dateElem = document.getElementById("currentDateStr");
  if (dateElem) {
    dateElem.textContent = new Date().toLocaleDateString(undefined, options);
  }
}

function formatDateSnippet(dateStr) {
  if (!dateStr) return "";
  try {
    const parts = dateStr.split(" ");
    if (parts.length === 2) {
      return `${parts[0]}`;
    }
    return dateStr;
  } catch (e) {
    return dateStr;
  }
}

function getCategoryIcon(cat) {
  const c = (cat || "").toLowerCase();
  if (c === "work") return "💼";
  if (c === "personal") return "🏡";
  if (c === "ideas") return "💡";
  if (c === "meetings") return "🤝";
  if (c === "projects") return "🚀";
  if (c === "urgent") return "🔥";
  if (c === "study") return "📚";
  return "📝";
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

