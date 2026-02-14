// Use Tauri global (no npm build required)
const invoke = window.__TAURI__.core.invoke;

const form = document.getElementById("form-monitor");
const inputName = document.getElementById("input-name");
const inputListUrl = document.getElementById("input-list-url");
const inputKeywords = document.getElementById("input-keywords");
const inputRefresh = document.getElementById("input-refresh");
const listIdPreview = document.getElementById("list-id-preview");
const monitorsList = document.getElementById("monitors-list");
const tweetsList = document.getElementById("tweets-list");
const btnRefreshTweets = document.getElementById("btn-refresh-tweets");
const toastEl = document.getElementById("toast");
const panelMonitors = document.getElementById("panel-monitors");
const panelNotifications = document.getElementById("panel-notifications");

function showToast(message, type = "success") {
  toastEl.textContent = message;
  toastEl.className = "toast visible " + type;
  setTimeout(() => toastEl.classList.remove("visible"), 3000);
}

function parseKeywords(raw) {
  const text = raw.trim();
  if (!text) return [];
  return text
    .split(/[\n,]+/)
    .map((k) => k.trim())
    .filter(Boolean);
}

async function refreshListIdPreview() {
  const url = inputListUrl.value.trim();
  if (!url) {
    listIdPreview.textContent = "";
    return;
  }
  try {
    const id = await invoke("parse_list_url", { listUrl: url });
    listIdPreview.textContent = id ? `List ID: ${id}` : "Could not parse list ID from URL";
  } catch (e) {
    listIdPreview.textContent = "";
  }
}

inputListUrl.addEventListener("input", refreshListIdPreview);
inputListUrl.addEventListener("blur", refreshListIdPreview);

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = inputName.value.trim();
  const listUrl = inputListUrl.value.trim();
  const keywords = parseKeywords(inputKeywords.value);
  const refreshMinutes = parseInt(inputRefresh.value, 10) || 1;

  if (!name || !listUrl) {
    showToast("Name and list URL are required.", "error");
    return;
  }
  if (keywords.length === 0) {
    showToast("Add at least one keyword or phrase.", "error");
    return;
  }

  try {
    const monitor = await invoke("add_monitor", {
      name,
      listUrl,
      keywords,
      refreshMinutes: refreshMinutes >= 1 ? refreshMinutes : 1,
    });
    showToast("Monitor added.");
    inputName.value = "";
    inputListUrl.value = "";
    inputKeywords.value = "";
    listIdPreview.textContent = "";
    loadMonitors();
    try {
      await invoke("start_headless_monitor", { monitor });
      showToast("Headless monitor started in background.");
    } catch (startErr) {
      showToast("Monitor saved; headless start failed: " + (startErr?.toString() || startErr), "error");
    }
  } catch (err) {
    showToast(err?.toString() || "Failed to add monitor", "error");
  }
});

async function loadMonitors() {
  try {
    const list = await invoke("list_monitors");
    renderMonitors(list);
  } catch (err) {
    monitorsList.innerHTML = `<p class="empty-state">Failed to load monitors: ${err}</p>`;
  }
}

function renderMonitors(list) {
  if (!list || list.length === 0) {
    monitorsList.innerHTML = '<p class="empty-state">No monitors yet. Create one above.</p>';
    return;
  }

  monitorsList.innerHTML = list
    .map(
      (m) => `
    <div class="monitor-card" data-id="${m.id}">
      <h3>${escapeHtml(m.name)}</h3>
      <div class="meta">${escapeHtml(m.list_url)}</div>
      <div class="keywords-pill">
        ${m.keywords.map((k) => `<span class="keyword">${escapeHtml(k)}</span>`).join("")}
      </div>
      <div class="actions">
        <button type="button" data-action="start-headless" data-id="${m.id}">Start headless monitor</button>
        <button type="button" data-action="generate" data-id="${m.id}">Generate script</button>
        <button type="button" class="secondary" data-action="open" data-url="${escapeAttr(m.list_url)}">Open list in browser</button>
        <button type="button" class="danger" data-action="delete" data-id="${m.id}">Delete</button>
      </div>
    </div>
  `
    )
    .join("");

  monitorsList.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", handleMonitorAction);
  });
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function escapeAttr(s) {
  return s.replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function handleMonitorAction(e) {
  const btn = e.target;
  const action = btn.dataset.action;
  const id = btn.dataset.id;
  const url = btn.dataset.url;

  if (action === "open" && url) {
    try {
      await invoke("open_url", { url });
      showToast("Opened list in browser.");
    } catch (err) {
      showToast("Could not open URL.", "error");
    }
    return;
  }

  if (action === "delete" && id) {
    if (!confirm("Remove this monitor?")) return;
    try {
      await invoke("delete_monitor", { id });
      showToast("Monitor removed.");
      loadMonitors();
    } catch (err) {
      showToast(err?.toString() || "Failed to delete", "error");
    }
    return;
  }

  if (action === "start-headless" && id) {
    const list = await invoke("list_monitors");
    const monitor = list.find((m) => m.id === id);
    if (!monitor) {
      showToast("Monitor not found.", "error");
      return;
    }
    try {
      await invoke("start_headless_monitor", { monitor });
      showToast("Headless monitor started in background.");
    } catch (err) {
      showToast(err?.toString() || "Failed to start headless monitor", "error");
    }
    return;
  }

  if (action === "generate" && id) {
    const list = await invoke("list_monitors");
    const monitor = list.find((m) => m.id === id);
    if (!monitor) {
      showToast("Monitor not found.", "error");
      return;
    }
    try {
      const script = await invoke("generate_script", { monitor });
      await navigator.clipboard.writeText(script);
      showToast("Script copied to clipboard. Install it in Tampermonkey, then open the list URL.");
    } catch (err) {
      showToast(err?.toString() || "Failed to generate script", "error");
    }
  }
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    panelMonitors.classList.toggle("hidden", tab !== "monitors");
    panelNotifications.classList.toggle("hidden", tab !== "notifications");
    if (tab === "notifications") loadTweets();
  });
});

btnRefreshTweets.addEventListener("click", () => loadTweets());

async function loadTweets() {
  try {
    const tweets = await invoke("fetch_recent_tweets", { limit: 100 });
    renderTweets(tweets);
  } catch (err) {
    tweetsList.innerHTML = `<p class="empty-state">Could not load tweets. Is the API running? (python news/tweets_api.py) — ${escapeHtml(String(err))}</p>`;
  }
}

function renderTweets(tweets) {
  if (!tweets || tweets.length === 0) {
    tweetsList.innerHTML = '<p class="empty-state">No tweets yet. Run the Tampermonkey script on a list page and ensure python news/tweets_api.py is running.</p>';
    return;
  }
  tweetsList.innerHTML = tweets
    .map(
      (t) => `
    <div class="tweet-card">
      <div class="author">${t.url ? `<a href="${escapeAttr(t.url)}" target="_blank" rel="noopener">@${escapeHtml(t.author_handle || "?")}</a>` : escapeHtml("@" + (t.author_handle || "?"))}</div>
      <div class="time">${escapeHtml(t.inserted_at || t.posted_at || "")}</div>
      <div class="text">${escapeHtml(t.text || "")}</div>
    </div>
  `
    )
    .join("");
}

loadMonitors();
