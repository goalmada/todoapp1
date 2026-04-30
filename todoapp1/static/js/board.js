const COLUMN_LABELS = {
  inbox: "Inbox",
  next: "Next",
  in_progress: "In Progress",
  done: "Done",
};

const state = {
  tasks: [],
  meetings: [],
  statuses: ["inbox", "next", "in_progress", "done"],
  openTaskId: null,
};

// ---------- bootstrap ----------

document.addEventListener("DOMContentLoaded", async () => {
  setupAuthorChip();
  bindUI();
  await refreshBoard();
  connectStream();
});

function setupAuthorChip() {
  const chip = document.getElementById("who");
  const set = (name) => {
    chip.textContent = (name || "?").trim().slice(0, 2).toUpperCase();
    chip.title = name || "Click to set your name";
  };
  set(localStorage.getItem("author") || "");
  chip.addEventListener("click", () => {
    const v = prompt("Your name (shows on cards you create / drag):", localStorage.getItem("author") || "");
    if (v !== null) {
      localStorage.setItem("author", v);
      set(v);
    }
  });
}

function bindUI() {
  document.getElementById("open-meeting-modal").addEventListener("click", () => openModal("meeting-modal"));
  document.getElementById("open-new-task").addEventListener("click", () => openModal("new-task-modal"));
  document.querySelectorAll("[data-close-modal]").forEach(btn => {
    btn.addEventListener("click", e => closeModal(e.target.closest(".modal").id));
  });
  document.querySelectorAll(".modal").forEach(m => {
    m.addEventListener("click", e => { if (e.target === m) closeModal(m.id); });
  });
  document.getElementById("extract-btn").addEventListener("click", submitMeetingNotes);
  document.getElementById("create-task-btn").addEventListener("click", submitNewTask);
  document.getElementById("sheet-close").addEventListener("click", closeSheet);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal:not(.hidden)").forEach(m => closeModal(m.id));
      closeSheet();
    }
  });
}

function openModal(id) {
  document.getElementById(id).classList.remove("hidden");
}
function closeModal(id) {
  document.getElementById(id).classList.add("hidden");
}

// ---------- data ----------

async function refreshBoard() {
  const r = await fetch("/api/board");
  const data = await r.json();
  state.tasks = data.tasks;
  state.meetings = data.meetings;
  state.statuses = data.statuses;
  renderBoard();
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || r.statusText);
  }
  return r.status === 204 ? null : r.json();
}

// ---------- rendering ----------

function renderBoard() {
  const root = document.getElementById("board");
  root.innerHTML = "";
  for (const status of state.statuses) {
    const tasks = state.tasks
      .filter(t => t.status === status)
      .sort((a, b) => a.column_position - b.column_position);
    root.appendChild(renderColumn(status, tasks));
  }
  initSortable();
}

function renderColumn(status, tasks) {
  const col = document.createElement("section");
  col.className = "column";
  col.dataset.status = status;
  col.innerHTML = `
    <div class="column-head">
      <div class="column-title">${COLUMN_LABELS[status] || status}</div>
      <div class="column-count">${tasks.length}</div>
    </div>
    <div class="column-body" data-status="${status}"></div>
  `;
  const body = col.querySelector(".column-body");
  if (tasks.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = status === "inbox" ? "Drop notes to extract tasks" : "—";
    body.appendChild(empty);
  } else {
    tasks.forEach(t => body.appendChild(renderCard(t)));
  }
  return col;
}

function renderCard(task) {
  const el = document.createElement("article");
  el.className = "card" + (task.status === "done" ? " done" : "");
  el.dataset.id = task.id;
  const assigneeChip = task.assignee
    ? `<span class="avatar" title="${escapeHtml(task.assignee)}">${initials(task.assignee)}</span>`
    : "";
  const projectTag = task.project ? `<span class="tag">${escapeHtml(task.project)}</span>` : "";
  const urgency = task.urgency ? `<span class="urgency-dot urgency-${task.urgency}" title="${task.urgency}"></span>` : "";
  const auto = task.auto_completed ? `<span class="auto-badge">✓ auto</span>` : "";
  el.innerHTML = `
    <h3 class="card-title">${escapeHtml(task.title)}</h3>
    <div class="card-meta">
      ${urgency}
      ${projectTag}
      ${auto}
      ${assigneeChip}
    </div>
  `;
  el.addEventListener("click", () => openSheet(task.id));
  return el;
}

function initSortable() {
  document.querySelectorAll(".column-body").forEach(body => {
    new Sortable(body, {
      group: "board",
      animation: 160,
      easing: "cubic-bezier(.2,.7,.2,1)",
      ghostClass: "sortable-ghost",
      chosenClass: "sortable-chosen",
      onAdd: handleSortChange,
      onUpdate: handleSortChange,
    });
  });
}

async function handleSortChange() {
  const updates = [];
  document.querySelectorAll(".column-body").forEach(body => {
    const status = body.dataset.status;
    body.querySelectorAll(".card").forEach((card, i) => {
      const id = parseInt(card.dataset.id, 10);
      const task = state.tasks.find(t => t.id === id);
      if (!task) return;
      if (task.status !== status || task.column_position !== i) {
        updates.push({ id, status, column_position: i });
        task.status = status;
        task.column_position = i;
      }
    });
  });
  if (!updates.length) return;
  try {
    await api("/api/tasks/reorder", { method: "POST", body: JSON.stringify({ updates }) });
  } catch (e) {
    toast("Failed to save: " + e.message);
    refreshBoard();
  }
}

// ---------- side sheet ----------

async function openSheet(taskId) {
  state.openTaskId = taskId;
  const sheet = document.getElementById("sheet");
  sheet.classList.remove("hidden");
  sheet.classList.add("open");
  sheet.setAttribute("aria-hidden", "false");

  const meta = document.getElementById("sheet-meta");
  const body = document.getElementById("sheet-body");
  meta.textContent = "Loading...";
  body.innerHTML = "";

  const task = await api(`/api/tasks/${taskId}`);
  renderSheet(task);
}

function closeSheet() {
  state.openTaskId = null;
  const sheet = document.getElementById("sheet");
  sheet.classList.remove("open");
  sheet.setAttribute("aria-hidden", "true");
}

function renderSheet(task) {
  const meta = document.getElementById("sheet-meta");
  const projectChip = task.project ? `<span class="tag">${escapeHtml(task.project)}</span>` : "";
  const urgency = task.urgency ? `<span class="urgency-dot urgency-${task.urgency}"></span> ${task.urgency}` : "";
  meta.innerHTML = `${COLUMN_LABELS[task.status] || task.status} · ${projectChip} ${urgency}`;

  const body = document.getElementById("sheet-body");
  const status = task.status;
  const statusOptions = state.statuses
    .map(s => `<option value="${s}" ${s === status ? "selected" : ""}>${COLUMN_LABELS[s] || s}</option>`)
    .join("");

  const sourceSection = task.source_quote
    ? `
      <div class="section">
        <div class="section-label">From the meeting</div>
        <blockquote class="quote">${escapeHtml(task.source_quote)}</blockquote>
      </div>`
    : "";

  const transcriptSection = task.meeting && task.meeting.raw_text
    ? `
      <div class="section">
        <div class="section-label">Full notes — ${escapeHtml(task.meeting.title || "")}</div>
        <div class="transcript">${highlightQuote(task.meeting.raw_text, task.source_quote)}</div>
      </div>`
    : "";

  const logSection = task.log_entry
    ? `
      <div class="section">
        <div class="section-label">Closed by Claude Code ${task.auto_completed ? "(auto-matched)" : ""}</div>
        <div class="log-card">
          <div><strong>${escapeHtml(task.log_entry.task || "")}</strong></div>
          <div>${escapeHtml(task.log_entry.description || "")}</div>
          <div class="small">${escapeHtml(task.log_entry.project || "")} · ${escapeHtml(task.log_entry.date || "")}</div>
          ${task.log_entry.could_improve && task.log_entry.could_improve !== "n/a"
            ? `<div class="small" style="margin-top:6px;"><em>Could improve:</em> ${escapeHtml(task.log_entry.could_improve)}</div>`
            : ""}
        </div>
      </div>`
    : "";

  body.innerHTML = `
    <h1>${escapeHtml(task.title)}</h1>
    <div class="muted">Created ${formatDate(task.created_at)}${task.assignee ? " · " + escapeHtml(task.assignee) : ""}</div>

    <div class="section">
      <div class="section-label">Status</div>
      <select id="sheet-status">${statusOptions}</select>
    </div>

    <div class="section">
      <div class="section-label">Description</div>
      <textarea class="desc-edit" id="sheet-desc" placeholder="Add details...">${escapeHtml(task.description || "")}</textarea>
    </div>

    ${sourceSection}
    ${transcriptSection}
    ${logSection}

    <div class="sheet-actions">
      <button class="btn btn-danger" id="sheet-delete">Delete</button>
    </div>
  `;

  document.getElementById("sheet-status").addEventListener("change", async (e) => {
    await api(`/api/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify({ status: e.target.value }) });
  });
  let descTimer;
  document.getElementById("sheet-desc").addEventListener("input", (e) => {
    clearTimeout(descTimer);
    descTimer = setTimeout(() => {
      api(`/api/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify({ description: e.target.value }) });
    }, 600);
  });
  document.getElementById("sheet-delete").addEventListener("click", async () => {
    if (!confirm("Delete this task?")) return;
    await api(`/api/tasks/${task.id}`, { method: "DELETE" });
    closeSheet();
  });
}

// ---------- forms ----------

async function submitMeetingNotes() {
  const text = document.getElementById("meeting-text").value.trim();
  if (!text) {
    toast("Paste some notes first");
    return;
  }
  const status = document.getElementById("meeting-status");
  const btn = document.getElementById("extract-btn");
  status.textContent = "Extracting tasks...";
  btn.disabled = true;
  try {
    const author = localStorage.getItem("author") || null;
    const res = await api("/api/meetings", {
      method: "POST",
      body: JSON.stringify({ raw_text: text, author }),
    });
    const n = (res.tasks || []).length;
    if (res.warning) {
      toast(res.warning);
    } else if (res.error) {
      toast(res.error);
    } else {
      toast(`Extracted ${n} task${n === 1 ? "" : "s"}`);
    }
    document.getElementById("meeting-text").value = "";
    closeModal("meeting-modal");
    status.textContent = "";
  } catch (e) {
    toast("Failed: " + e.message);
    status.textContent = "";
  } finally {
    btn.disabled = false;
  }
}

async function submitNewTask() {
  const title = document.getElementById("new-task-title").value.trim();
  const desc = document.getElementById("new-task-desc").value.trim();
  if (!title) {
    toast("Title required");
    return;
  }
  await api("/api/tasks", {
    method: "POST",
    body: JSON.stringify({ title, description: desc, assignee: localStorage.getItem("author") || null }),
  });
  document.getElementById("new-task-title").value = "";
  document.getElementById("new-task-desc").value = "";
  closeModal("new-task-modal");
}

// ---------- streaming ----------

function connectStream() {
  let backoff = 1000;
  const open = () => {
    const es = new EventSource("/api/stream");
    es.addEventListener("hello", () => { backoff = 1000; });
    const dirty = () => refreshBoard();
    ["task_added", "task_updated", "task_deleted", "meeting_added", "board_reordered", "log_entry"].forEach(ev => {
      es.addEventListener(ev, async (e) => {
        if (ev === "log_entry") {
          const data = JSON.parse(e.data || "{}");
          if (data.matched_task_id) {
            toast("Closed by Claude Code");
          }
        }
        dirty();
        if (state.openTaskId) {
          const t = await api(`/api/tasks/${state.openTaskId}`);
          renderSheet(t);
        }
      });
    });
    es.onerror = () => {
      es.close();
      setTimeout(open, backoff);
      backoff = Math.min(backoff * 2, 15000);
    };
  };
  open();
}

// ---------- helpers ----------

function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function highlightQuote(text, quote) {
  const safe = escapeHtml(text);
  if (!quote) return safe;
  const safeQuote = escapeHtml(quote);
  const idx = safe.indexOf(safeQuote);
  if (idx < 0) return safe;
  return safe.slice(0, idx) + "<mark>" + safe.slice(idx, idx + safeQuote.length) + "</mark>" + safe.slice(idx + safeQuote.length);
}

function initials(name) {
  return name.split(/\s+/).filter(Boolean).map(w => w[0]).slice(0, 2).join("").toUpperCase();
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

let toastTimer;
function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2400);
}
