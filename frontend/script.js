/**
 * Personal Notes Management Web App - Frontend Script
 * Handles Username-based Authentication, Zone isolation (Chilaw, Puttalam, Middle Zone),
 * dynamic Customer Name & Farm Name with Code dropdowns from Running List.xlsx,
 * and bidirectional Streamlit component communication.
 */

// Application State
let appState = {
  authenticated: false,
  user: null,
  notes: [],
  runningList: {
    zone: "",
    total_items: 0,
    customers: [],
    farms: [],
    items: [],
  },
  allZones: [],
  backendStatus: {
    drive: { is_connected: false, status_message: "Checking..." },
    firebase: { is_live: false, status_message: "Checking..." },
  },
  filter: {
    search: "",
    customer: "",
    farm: "",
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
        height: Math.max(scrollH, 920),
      },
      "*"
    );
  }, 60);
}

// Receive messages from Streamlit parent window
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

  if (serverState.running_list) {
    appState.runningList = serverState.running_list;
  }
  if (serverState.all_zones) {
    appState.allZones = serverState.all_zones;
  }
  if (serverState.backend_status) {
    appState.backendStatus = serverState.backend_status;
  }

  // Handle alerts & toasts
  if (serverState.error) {
    showAuthError(serverState.error);
    showToast(serverState.error, "error");
  } else {
    hideAuthError();
  }

  if (serverState.toast) {
    showToast(serverState.toast, "success");
  }

  // Render proper view
  if (appState.authenticated && appState.user) {
    showDashboardView();
  } else {
    showAuthView();
  }

  updateFrameHeight();
}

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

  const user = appState.user || { name: "Officer", username: "user", zone: "Chilaw", uid: "" };
  const userZone = user.zone || "Chilaw";

  // Navigation user profile
  document.getElementById("welcomeUserName").textContent = user.name || user.username || "Officer";
  document.getElementById("welcomeUserZonePill").textContent = `📍 ${userZone} Zone`;
  document.getElementById("navUserName").textContent = user.name || user.username || "Officer";
  document.getElementById("navUserZoneSnippet").textContent = `${userZone} • ${(user.uid || "").slice(0, 12)}...`;
  document.getElementById("userAvatarText").textContent = (user.name || "O").charAt(0).toUpperCase();
  document.getElementById("userZoneBadgeText").textContent = `${userZone} Zone`;

  // System status
  const drive = appState.backendStatus.drive || {};
  const driveLabel = document.getElementById("driveStatusLabel");
  const drivePill = document.getElementById("driveStatusPill");
  if (drive.is_connected) {
    driveLabel.textContent = "Drive: Connected";
    drivePill.querySelector(".status-dot").className = "status-dot";
  } else {
    driveLabel.textContent = "Drive: Local Excel";
    drivePill.querySelector(".status-dot").className = "status-dot local-mode";
  }

  // Populate Customer and Farm dropdowns from Running List data for this user's zone
  populateZoneDropdowns();

  // Render Notes
  renderNotes();
}

function handleLoginSubmit(event) {
  event.preventDefault();
  hideAuthError();

  const username = document.getElementById("loginUsername").value.trim();
  const password = document.getElementById("loginPassword").value;

  if (!username || !password) {
    showAuthError("Please enter both username and password.");
    return;
  }

  const submitBtn = document.getElementById("loginSubmitBtn");
  submitBtn.disabled = true;
  submitBtn.innerHTML = "<span>Signing in...</span>";

  sendToStreamlit("login", {
    username: username,
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
// RUNNING LIST DROPDOWNS & DYNAMIC LINKING
// ===================================================================

function populateZoneDropdowns() {
  const rl = appState.runningList || {};
  const customers = rl.customers || [];
  const farms = rl.farms || [];

  // Update stat cards
  document.getElementById("statZoneCustomers").textContent = customers.length;
  document.getElementById("statZoneFarms").textContent = farms.length;

  // 1. Dashboard Controls Selectors
  populateSelectOptions("dashboardCustomerSelect", customers, "-- Choose Customer --");
  populateSelectOptions("dashboardFarmSelect", farms, "-- Choose Farm with Code --");

  // 2. Modal Selectors
  populateSelectOptions("modalCustomerSelect", customers, "-- Choose Customer --");
  populateSelectOptions("modalFarmSelect", farms, "-- Choose Farm with Code --");

  // 3. Filter Toolbar Selectors
  populateSelectOptions("filterCustomer", customers, "All Customers in My Zone");
  populateSelectOptions("filterFarm", farms, "All Farms with Code");
}

function populateSelectOptions(selectId, optionsList, defaultLabel) {
  const select = document.getElementById(selectId);
  if (!select) return;

  const currentVal = select.value;
  select.innerHTML = `<option value="">${defaultLabel}</option>`;

  optionsList.forEach((opt) => {
    const el = document.createElement("option");
    el.value = opt;
    el.textContent = opt;
    select.appendChild(el);
  });

  if (currentVal && optionsList.includes(currentVal)) {
    select.value = currentVal;
  }
}

// Dynamic linking on Dashboard Controls
function handleDashboardCustomerChange() {
  const cust = document.getElementById("dashboardCustomerSelect").value;
  if (!cust) return;

  const rl = appState.runningList || {};
  const matchingItems = (rl.items || []).filter((it) => it.customer === cust);

  if (matchingItems.length > 0) {
    const farmSelect = document.getElementById("dashboardFarmSelect");
    farmSelect.value = matchingItems[0].farm;
  }
}

function handleDashboardFarmChange() {
  const farm = document.getElementById("dashboardFarmSelect").value;
  if (!farm) return;

  const rl = appState.runningList || {};
  const item = (rl.items || []).find((it) => it.farm === farm);

  if (item && item.customer) {
    const custSelect = document.getElementById("dashboardCustomerSelect");
    custSelect.value = item.customer;
  }
}

// Dynamic linking inside the Modal
function handleModalCustomerChange() {
  const cust = document.getElementById("modalCustomerSelect").value;
  if (!cust) return;

  const rl = appState.runningList || {};
  const matchingItems = (rl.items || []).filter((it) => it.customer === cust);

  if (matchingItems.length > 0) {
    const farmSelect = document.getElementById("modalFarmSelect");
    farmSelect.value = matchingItems[0].farm;
  }
}

function handleModalFarmChange() {
  const farm = document.getElementById("modalFarmSelect").value;
  if (!farm) return;

  const rl = appState.runningList || {};
  const item = (rl.items || []).find((it) => it.farm === farm);

  if (item && item.customer) {
    const custSelect = document.getElementById("modalCustomerSelect");
    custSelect.value = item.customer;
  }
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

  const searchTerm = (appState.filter.search || "").toLowerCase().trim();
  const filterCust = appState.filter.customer;
  const filterFarm = appState.filter.farm;

  const filtered = notes.filter((n) => {
    const cust = (n.customer_name || n.selection1 || "").toLowerCase();
    const farm = (n.farm_name || n.selection2 || "").toLowerCase();
    const content = (n.content || "").toLowerCase();

    const matchesSearch =
      !searchTerm ||
      content.includes(searchTerm) ||
      cust.includes(searchTerm) ||
      farm.includes(searchTerm);

    const matchesCustomer = !filterCust || (n.customer_name || n.selection1) === filterCust;
    const matchesFarm = !filterFarm || (n.farm_name || n.selection2) === filterFarm;

    return matchesSearch && matchesCustomer && matchesFarm;
  });

  document.getElementById("statTotalNotes").textContent = notes.length;

  if (filtered.length === 0) {
    emptyState.style.display = "block";
    if (notes.length > 0) {
      emptyMsg.textContent = "No notes matched your search or customer/farm filter criteria.";
    } else {
      emptyMsg.textContent = `You haven't recorded any notes for ${appState.user?.zone || "your"} zone yet. Click below to add your first note!`;
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
  card.className = "note-card clickable-card";
  card.id = `card-${note.note_id}`;
  card.setAttribute("onclick", `openViewNoteModal('${note.note_id}')`);
  card.title = "Click to view full note details";

  const customerName = note.customer_name || note.selection1 || "Unknown Customer";
  const farmName = note.farm_name || note.selection2 || "No Farm Assigned";
  const noteZone = note.zone || appState.user?.zone || "";
  const displayDate = note.updated_date || note.created_date || "Just now";
  const rawContent = note.content || "";
  const safeContent = escapeHtml(rawContent);
  const isLong = rawContent.length > 100 || rawContent.includes("\n");

  card.innerHTML = `
    <div class="card-header">
      <div class="card-badges">
        <span class="tag-badge tag-badge-customer" title="Customer: ${escapeHtml(customerName)}">
          👤 ${escapeHtml(customerName)}
        </span>
        <span class="tag-badge tag-badge-farm" title="Farm with Code: ${escapeHtml(farmName)}">
          🌾 ${escapeHtml(farmName)}
        </span>
        ${noteZone ? `<span class="tag-badge tag-badge-zone">📍 ${escapeHtml(noteZone)}</span>` : ""}
      </div>
      <span class="card-timestamp" title="Recorded: ${displayDate}">${formatDateSnippet(displayDate)}</span>
    </div>

    <div class="card-body">
      <p class="note-content-text note-content-clamp">${safeContent}</p>
      ${isLong ? `<div class="view-more-hint">Tap card to view full details &rarr;</div>` : ""}
    </div>

    <div class="card-footer">
      <span class="note-id-pill" title="ID: ${note.note_id}">${note.note_id.slice(0, 12)}</span>
      <div class="card-actions">
        <button class="action-icon-btn delete-btn" onclick="event.stopPropagation(); openDeleteModal('${note.note_id}')" title="Delete note">
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

function handleSearchFilterChange() {
  const searchInput = document.getElementById("searchNotesInput");
  const clearBtn = document.getElementById("clearSearchBtn");
  const filterCust = document.getElementById("filterCustomer").value;
  const filterFarm = document.getElementById("filterFarm").value;

  appState.filter.search = searchInput.value;
  appState.filter.customer = filterCust;
  appState.filter.farm = filterFarm;

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
// NOTE DETAILS MODAL (FULL VIEW)
// ===================================================================

let currentViewNoteId = null;

function openViewNoteModal(noteId) {
  const note = (appState.notes || []).find((n) => n.note_id === noteId);
  if (!note) return;

  currentViewNoteId = note.note_id;
  const cust = note.customer_name || note.selection1 || "Unknown Customer";
  const farm = note.farm_name || note.selection2 || "No Farm Assigned";
  const zone = note.zone || appState.user?.zone || "Zone";
  const date = note.created_date || note.updated_date || "Date not recorded";

  document.getElementById("viewModalCustomer").textContent = cust;
  document.getElementById("viewModalFarm").textContent = farm;
  document.getElementById("viewModalZone").textContent = `📍 ${zone}`;
  document.getElementById("viewModalDate").textContent = `Recorded: ${date}`;
  document.getElementById("viewModalId").textContent = `ID: ${note.note_id}`;
  document.getElementById("viewModalContent").textContent = note.content || "";

  document.getElementById("viewNoteModal").style.display = "flex";
}

function closeViewNoteModal() {
  currentViewNoteId = null;
  document.getElementById("viewNoteModal").style.display = "none";
}

function handleViewModalDelete() {
  const idToDelete = currentViewNoteId;
  closeViewNoteModal();
  if (idToDelete) {
    openDeleteModal(idToDelete);
  }
}

// ===================================================================
// ADD NOTE MODAL
// ===================================================================

function openAddNoteModal() {
  const dashCust = document.getElementById("dashboardCustomerSelect").value;
  const dashFarm = document.getElementById("dashboardFarmSelect").value;

  document.getElementById("modalTitle").textContent = "Record Field Note";
  document.getElementById("modalSaveBtnText").textContent = "Save Note";
  document.getElementById("modalNoteId").value = "";
  document.getElementById("modalCustomerSelect").value = dashCust || "";
  document.getElementById("modalFarmSelect").value = dashFarm || "";
  document.getElementById("modalNoteContent").value = "";
  updateCharCount();

  document.getElementById("noteModal").style.display = "flex";
  setTimeout(() => document.getElementById("modalNoteContent").focus(), 100);
}

function closeNoteModal() {
  document.getElementById("noteModal").style.display = "none";
}

function handleSaveNote(event) {
  event.preventDefault();

  const cust = document.getElementById("modalCustomerSelect").value;
  const farm = document.getElementById("modalFarmSelect").value;
  const content = document.getElementById("modalNoteContent").value.trim();

  if (!cust) {
    showToast("Please choose a Customer Name.", "error");
    return;
  }
  if (!farm) {
    showToast("Please choose a Farm Name with Code.", "error");
    return;
  }
  if (!content) {
    showToast("Please enter some note content.", "error");
    return;
  }

  const saveBtn = document.getElementById("modalSaveBtn");
  saveBtn.disabled = true;

  sendToStreamlit("add_note", {
    customer_name: cust,
    farm_name: farm,
    content: content,
  });

  closeNoteModal();
  setTimeout(() => {
    saveBtn.disabled = false;
  }, 500);
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
  const cust = note.customer_name || note.selection1 || "";
  const farm = note.farm_name || note.selection2 || "";
  preview.textContent = `[${cust} • ${farm}]\n${(note.content || "").slice(0, 140)}...`;

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

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeNoteModal();
    closeDeleteModal();
    closeViewNoteModal();
  }
});

document.addEventListener("click", (e) => {
  const noteModal = document.getElementById("noteModal");
  const deleteModal = document.getElementById("deleteModal");
  const viewModal = document.getElementById("viewNoteModal");
  if (e.target === noteModal) closeNoteModal();
  if (e.target === deleteModal) closeDeleteModal();
  if (e.target === viewModal) closeViewNoteModal();
});

// ===================================================================
// UTILITIES & TOASTS
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
    return parts[0] || dateStr;
  } catch (e) {
    return dateStr;
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}
