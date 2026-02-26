// Use Tauri global (no npm build required). Never throw at load so all buttons get their handlers.
var invoke, listen;
try {
  var t = window.__TAURI__;
  invoke = t && t.core && t.core.invoke ? t.core.invoke : null;
  listen = (t && (t.event?.listen ?? t.core?.event?.listen)) || null;
} catch (_) {
  invoke = null;
  listen = null;
}
if (!invoke) {
  invoke = function () { return Promise.reject(new Error("Tauri not ready")); };
}

function initApp() {
const form = document.getElementById("form-monitor");
const inputName = document.getElementById("input-name");
const inputListUrl = document.getElementById("input-list-url");
const inputKeywords = document.getElementById("input-keywords");
const inputRefresh = document.getElementById("input-refresh");
const inputFeed = document.getElementById("input-feed");
const listIdPreview = document.getElementById("list-id-preview");
const tableNamePreview = document.getElementById("table-name-preview");
const btnCreateDbTable = document.getElementById("btn-create-db-table");
const monitorsList = document.getElementById("monitors-list");
const tweetsList = document.getElementById("tweets-list");
const tweetsListAll = document.getElementById("tweets-list-all");
const tweetsListGolf = document.getElementById("tweets-list-golf");
const btnRefreshTweets = document.getElementById("btn-refresh-tweets");
const btnRefreshTweetsAll = document.getElementById("btn-refresh-tweets-all");
const btnRefreshTweetsGolf = document.getElementById("btn-refresh-tweets-golf");
const notificationsSubNav = document.getElementById("notifications-sub-nav");
const feedMlb = document.getElementById("feed-mlb");
const feedGolf = document.getElementById("feed-golf");
const feedNfl = document.getElementById("feed-nfl");
const feedPolitics = document.getElementById("feed-politics");
const mlbSectionView = document.getElementById("mlb-section-view");
const mlbAlertsView = document.getElementById("mlb-alerts-view");
const mlbSearchAllView = document.getElementById("mlb-search-all-view");
const linkMlbAlerts = document.getElementById("link-mlb-alerts");
const linkMlbSearchAll = document.getElementById("link-mlb-search-all");
const backFromMlbAlerts = document.getElementById("back-from-mlb-alerts");
const backFromMlbSearchAll = document.getElementById("back-from-mlb-search-all");
const searchAllKeywordsInput = document.getElementById("search-all-keywords");
const btnClearSearchAll = document.getElementById("btn-clear-search-all");
const toastEl = document.getElementById("toast");
const panelHome = document.getElementById("panel-home");
const panelMonitors = document.getElementById("panel-monitors");
const panelNotifications = document.getElementById("panel-notifications");
const panelKalshi = document.getElementById("panel-kalshi");
const serverStatusEl = document.getElementById("server-status");
const btnServerToggle = document.getElementById("btn-server-toggle");
const kalshiServerStatusEl = document.getElementById("kalshi-server-status");
const btnKalshiServerToggle = document.getElementById("btn-kalshi-server-toggle");
const kalshiEnvSelect = document.getElementById("kalshi-env");
const btnKalshiRefresh = document.getElementById("btn-kalshi-refresh");
const kalshiBalanceEl = document.getElementById("kalshi-balance");
const kalshiExchangeStatusEl = document.getElementById("kalshi-exchange-status");
const kalshiOrdersListEl = document.getElementById("kalshi-orders-list");
const kalshiPositionsListEl = document.getElementById("kalshi-positions-list");
const formKalshiOrder = document.getElementById("form-kalshi-order");
const kalshiOrderTicker = document.getElementById("kalshi-order-ticker");
const kalshiOrderSides = document.getElementById("kalshi-order-sides");
const kalshiOrderCount = document.getElementById("kalshi-order-count");
const kalshiOrderYesPrice = document.getElementById("kalshi-order-yes-price");
const kalshiOrderNoPrice = document.getElementById("kalshi-order-no-price");
const kalshiOrderExpiration = document.getElementById("kalshi-order-expiration");
const kalshiOrderExpirationDatetime = document.getElementById("kalshi-order-expiration-datetime");
const kalshiOrderExpirationDatetimeWrap = document.getElementById("kalshi-order-expiration-datetime-wrap");
const kalshiOrderReciprocal = document.getElementById("kalshi-order-reciprocal");
const kalshiBatchListEl = document.getElementById("kalshi-batch-list");
const btnKalshiPlaceBatch = document.getElementById("btn-kalshi-place-batch");
const btnKalshiClearBatch = document.getElementById("btn-kalshi-clear-batch");
const kalshiEventTicker = document.getElementById("kalshi-event-ticker");
const kalshiMarketsStatus = document.getElementById("kalshi-markets-status");
const kalshiMarketsSort = document.getElementById("kalshi-markets-sort");
const btnKalshiLoadMarkets = document.getElementById("btn-kalshi-load-markets");
const kalshiMarketsListEl = document.getElementById("kalshi-markets-list");
const kalshiMarketsRequestUrlEl = document.getElementById("kalshi-markets-request-url");

let kalshiBatchTickers = [];

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

async function refreshTableNamePreview() {
  const name = inputName.value.trim();
  if (!tableNamePreview) return;
  if (!name) {
    tableNamePreview.textContent = "";
    return;
  }
  try {
    const tableName = await invoke("derive_tweets_table_name", { monitorName: name });
    tableNamePreview.textContent = tableName ? `Table: ${tableName}` : "";
  } catch (e) {
    tableNamePreview.textContent = "";
  }
}
inputName.addEventListener("input", refreshTableNamePreview);
inputName.addEventListener("blur", refreshTableNamePreview);

async function loadTablesDropdown() {
  if (!inputFeed) return;
  try {
    const tables = await invoke("list_tweets_tables", {});
    inputFeed.innerHTML = (tables && tables.length)
      ? tables.map((t) => `<option value="${escapeAttr(t)}">${escapeHtml(t)}</option>`).join("")
      : '<option value="mlb_tweets">mlb_tweets</option>';
    if (tables && tables.length && !inputFeed.value) inputFeed.selectedIndex = 0;
  } catch (e) {
    inputFeed.innerHTML = '<option value="mlb_tweets">mlb_tweets (API not running?)</option>';
  }
}

if (btnCreateDbTable) {
  btnCreateDbTable.addEventListener("click", async () => {
    const name = inputName.value.trim();
    if (!name) {
      showToast("Enter a monitor name first.", "error");
      return;
    }
    try {
      const tableName = await invoke("create_tweets_table", { monitorName: name });
      showToast(`Table ${tableName} created in news_sources.`);
    } catch (err) {
      showToast(err?.toString() || "Failed to create table (is the API running?)", "error");
    }
  });
}

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
    const feed = (inputFeed && inputFeed.value) ? inputFeed.value.trim() : "mlb_tweets";
    const monitor = await invoke("add_monitor", {
      name,
      listUrl,
      keywords,
      refreshMinutes: refreshMinutes >= 1 ? refreshMinutes : 1,
      feed: feed || "mlb_tweets",
    });
    showToast("Monitor added.");
    inputName.value = "";
    inputListUrl.value = "";
    inputKeywords.value = "";
    listIdPreview.textContent = "";
    loadMonitors();
    try {
      await invoke("start_headless_monitor", { monitor });
      showToast("List monitor started in background (scrapes every 60s).");
    } catch (startErr) {
      showToast("Monitor saved; list monitor start failed: " + (startErr?.toString() || startErr), "error");
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
      (m) => {
        const tableLabel = (m.feed && m.feed.trim()) ? m.feed.trim() : "mlb_tweets";
        return `
    <div class="monitor-card" data-id="${m.id}">
      <h3>${escapeHtml(m.name)}</h3>
      <div class="meta">Table: ${escapeHtml(tableLabel)} · ${escapeHtml(m.list_url)}</div>
      <div class="keywords-pill">
        ${m.keywords.map((k) => `<span class="keyword">${escapeHtml(k)}</span>`).join("")}
      </div>
      <div class="actions">
        <button type="button" data-action="start-headless" data-id="${m.id}">Start list monitor</button>
        <button type="button" data-action="generate" data-id="${m.id}">Generate script</button>
        <button type="button" data-action="generate-scrape-all" data-id="${m.id}">Generate scrape-all script</button>
        <button type="button" class="secondary" data-action="open" data-url="${escapeAttr(m.list_url)}">Open list in browser</button>
        <button type="button" class="danger" data-action="delete" data-id="${m.id}">Delete</button>
      </div>
    </div>
  `;
      }
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
      showToast("List monitor started in background (scrapes every 60s).");
    } catch (err) {
      showToast(err?.toString() || "Failed to start list monitor", "error");
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
      showToast("Script copied to clipboard. Install in Tampermonkey, then open the list URL. Run python news/tweets_api.py for DB uploads.");
    } catch (err) {
      showToast(err?.toString() || "Failed to generate script", "error");
    }
    return;
  }

  if (action === "generate-scrape-all" && id) {
    const list = await invoke("list_monitors");
    const monitor = list.find((m) => m.id === id);
    if (!monitor) {
      showToast("Monitor not found.", "error");
      return;
    }
    try {
      const script = await invoke("generate_scrape_all_script", { monitor });
      await navigator.clipboard.writeText(script);
      showToast("Scrape-all script copied. POSTs to /api/tweet/all (e.g. mlb_tweets_all).");
    } catch (err) {
      showToast(err?.toString() || "Failed to generate scrape-all script", "error");
    }
  }
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    panelHome.classList.toggle("hidden", tab !== "home");
    panelMonitors.classList.toggle("hidden", tab !== "monitors");
    panelNotifications.classList.toggle("hidden", tab !== "notifications");
    if (panelKalshi) panelKalshi.classList.toggle("hidden", tab !== "kalshi");
    if (tab === "kalshi") refreshKalshiStatus();
    if (tab === "monitors") loadTablesDropdown();
    if (tab === "notifications") {
      showNotificationsHome();
    }
    // Home tab: no auto-check; status stays "Server: Unknown" until user clicks Start/Stop server
  });
});

function applyServerStatusUI(running, err) {
  if (!serverStatusEl || !btnServerToggle) return;
  if (err || running === null) {
    serverStatusEl.textContent = "Server: Unknown";
    serverStatusEl.className = "status-pill status-unknown";
    btnServerToggle.textContent = "Start server";
  } else if (running) {
    serverStatusEl.textContent = "Server: Running";
    serverStatusEl.className = "status-pill status-on";
    btnServerToggle.textContent = "Stop server";
  } else {
    serverStatusEl.textContent = "Server: Stopped";
    serverStatusEl.className = "status-pill status-off";
    btnServerToggle.textContent = "Start server";
  }
}

function runServerToggle(running) {
  (async () => {
    try {
      if (running) {
        btnServerToggle.textContent = "Stopping…";
        await invoke("stop_tweets_server");
        showToast("Tweets API server stopped.");
        applyServerStatusUI(false, null);
      } else {
        btnServerToggle.textContent = "Starting…";
        await Promise.race([
          invoke("start_tweets_server"),
          new Promise((_, reject) => setTimeout(() => reject(new Error("Start timed out (15s). Check news/tweets_api_stderr.log")), 15000)),
        ]);
        showToast("Tweets API server started.");
        applyServerStatusUI(true, null);
      }
    } catch (err) {
      showToast(err?.toString() || "Failed to toggle server", "error");
      applyServerStatusUI(null, true);
    } finally {
      btnServerToggle.disabled = false;
    }
  })();
}

if (btnServerToggle) {
  btnServerToggle.addEventListener("click", () => {
    if (btnServerToggle.disabled) return;
    btnServerToggle.disabled = true;
    if (serverStatusEl) serverStatusEl.textContent = "Checking…";

    if (typeof listen !== "function") {
      // Event API not available (e.g. .event undefined at load). Use blocking check; may freeze briefly.
      invoke("tweets_server_status_blocking")
        .then((running) => runServerToggle(running))
        .catch(() => {
          applyServerStatusUI(null, true);
          btnServerToggle.disabled = false;
        });
      return;
    }

    let unlistenFn = null;
    const timeout = setTimeout(() => {
      if (unlistenFn) try { unlistenFn(); } catch (_) {}
      applyServerStatusUI(null, true);
      btnServerToggle.disabled = false;
    }, 6000);
    listen("tweets-server-status", function (ev) {
      clearTimeout(timeout);
      const running = ev.payload;
      if (unlistenFn) try { unlistenFn(); } catch (_) {}
      runServerToggle(running);
    })
      .then((unlisten) => {
        unlistenFn = unlisten;
        invoke("tweets_server_status").catch(() => {
          clearTimeout(timeout);
          applyServerStatusUI(null, true);
          btnServerToggle.disabled = false;
        });
      })
      .catch(() => {
        clearTimeout(timeout);
        applyServerStatusUI(null, true);
        btnServerToggle.disabled = false;
      });
  });
}

let currentNotificationFeed = "mlb";
let showingNotificationsSubNav = true;

function showNotificationsHome() {
  showingNotificationsSubNav = true;
  if (notificationsSubNav) notificationsSubNav.classList.remove("hidden");
  document.querySelectorAll(".feed-content").forEach((el) => el.classList.add("hidden"));
  const activeFeedEl = document.getElementById("feed-" + currentNotificationFeed);
  if (activeFeedEl) activeFeedEl.classList.remove("hidden");
  document.querySelectorAll(".sub-tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.feed === currentNotificationFeed));
  if (currentNotificationFeed === "mlb") {
    mlbSectionView.classList.remove("hidden");
    mlbAlertsView.classList.add("hidden");
    mlbSearchAllView.classList.add("hidden");
  }
}

function showFeedContent(feed) {
  currentNotificationFeed = feed;
  showingNotificationsSubNav = false;
  if (notificationsSubNav) notificationsSubNav.classList.add("hidden");
  document.querySelectorAll(".feed-content").forEach((el) => el.classList.add("hidden"));
  const activeFeedEl = document.getElementById("feed-" + feed);
  if (activeFeedEl) activeFeedEl.classList.remove("hidden");
  if (feed === "mlb") {
    mlbSectionView.classList.remove("hidden");
    mlbAlertsView.classList.add("hidden");
    mlbSearchAllView.classList.add("hidden");
  }
  if (feed === "golf") loadTweetsGolf();
}

function showMlbSection() {
  mlbSectionView.classList.remove("hidden");
  mlbAlertsView.classList.add("hidden");
  mlbSearchAllView.classList.add("hidden");
}

function showMlbAlerts() {
  mlbSectionView.classList.add("hidden");
  mlbAlertsView.classList.remove("hidden");
  mlbSearchAllView.classList.add("hidden");
  loadTweets();
}

let lastTweetsAll = [];

function showMlbSearchAll() {
  mlbSectionView.classList.add("hidden");
  mlbAlertsView.classList.add("hidden");
  mlbSearchAllView.classList.remove("hidden");
  if (searchAllKeywordsInput) searchAllKeywordsInput.value = "";
  loadTweetsAll();
}

if (notificationsSubNav) {
  notificationsSubNav.querySelectorAll(".sub-tab").forEach((btn) => {
    btn.addEventListener("click", () => showFeedContent(btn.dataset.feed));
  });
}
if (linkMlbAlerts) linkMlbAlerts.addEventListener("click", (e) => { e.preventDefault(); showMlbAlerts(); });
if (linkMlbSearchAll) linkMlbSearchAll.addEventListener("click", (e) => { e.preventDefault(); showMlbSearchAll(); });
if (backFromMlbAlerts) backFromMlbAlerts.addEventListener("click", (e) => { e.preventDefault(); showMlbSection(); });
if (backFromMlbSearchAll) backFromMlbSearchAll.addEventListener("click", (e) => { e.preventDefault(); showMlbSection(); });

btnRefreshTweets.addEventListener("click", () => loadTweets());
if (btnRefreshTweetsAll) btnRefreshTweetsAll.addEventListener("click", () => loadTweetsAll());
if (btnRefreshTweetsGolf) btnRefreshTweetsGolf.addEventListener("click", () => loadTweetsGolf());

// Open external tweet links in system browser (Tauri webview doesn't follow target="_blank")
document.body.addEventListener("click", (e) => {
  const a = e.target.closest("a.open-in-browser");
  if (!a || !a.dataset.url) return;
  e.preventDefault();
  invoke("open_url", { url: a.dataset.url }).catch(() => {});
});
if (searchAllKeywordsInput) {
  searchAllKeywordsInput.addEventListener("input", () => applySearchAllFilter());
  searchAllKeywordsInput.addEventListener("keydown", (e) => { if (e.key === "Escape") { searchAllKeywordsInput.value = ""; applySearchAllFilter(); searchAllKeywordsInput.blur(); } });
}
if (btnClearSearchAll) btnClearSearchAll.addEventListener("click", () => { if (searchAllKeywordsInput) searchAllKeywordsInput.value = ""; applySearchAllFilter(); searchAllKeywordsInput.focus(); });

async function loadTweets() {
  try {
    const tweets = await invoke("fetch_recent_tweets", { limit: 100 });
    renderTweets(tweets, tweetsList);
  } catch (err) {
    tweetsList.innerHTML = `<p class="empty-state">Could not load tweets. Is the API running? (python news/tweets_api.py) — ${escapeHtml(String(err))}</p>`;
  }
}

async function loadTweetsAll() {
  if (!tweetsListAll) return;
  try {
    const tweets = await invoke("fetch_recent_tweets_all", { limit: 500 });
    lastTweetsAll = tweets || [];
    applySearchAllFilter();
  } catch (err) {
    lastTweetsAll = [];
    tweetsListAll.innerHTML = `<p class="empty-state">Could not load tweets. Is the API running? — ${escapeHtml(String(err))}</p>`;
  }
}

async function loadTweetsGolf() {
  if (!tweetsListGolf) return;
  try {
    const tweets = await invoke("fetch_recent_tweets_golf", { limit: 100 });
    renderTweets(tweets, tweetsListGolf);
  } catch (err) {
    tweetsListGolf.innerHTML = `<p class="empty-state">Could not load tweets. Is the API running? — ${escapeHtml(String(err))}</p>`;
  }
}

function applySearchAllFilter() {
  if (!tweetsListAll) return;
  const q = (searchAllKeywordsInput && searchAllKeywordsInput.value.trim()) || "";
  const keywords = q ? q.toLowerCase().split(/\s+/).filter(Boolean) : [];
  const filtered = keywords.length === 0
    ? lastTweetsAll
    : lastTweetsAll.filter((t) => {
        const text = ((t.text || "") + " " + (t.author_handle || "")).toLowerCase();
        return keywords.every((kw) => text.includes(kw));
      });
  if (lastTweetsAll.length === 0) {
    tweetsListAll.innerHTML = '<p class="empty-state">No tweets yet. Run the scrape-all Tampermonkey script and ensure python news/tweets_api.py is running.</p>';
  } else if (keywords.length > 0 && filtered.length === 0) {
    tweetsListAll.innerHTML = '<p class="empty-state search-no-results">No tweets match your search.</p>';
  } else {
    renderTweets(filtered, tweetsListAll);
  }
}

function renderTweets(tweets, container) {
  const el = container || tweetsList;
  if (!tweets || tweets.length === 0) {
    el.innerHTML = '<p class="empty-state">No tweets yet. Run the list monitor (or scrape-all script) and ensure python news/tweets_api.py is running.</p>';
    return;
  }
  el.innerHTML = tweets
    .map(
      (t) => {
        const tweetUrl = t.url || (t.tweet_id && t.author_handle ? `https://x.com/${encodeURIComponent(t.author_handle)}/status/${t.tweet_id}` : null);
        const handleDisplay = escapeHtml("@" + (t.author_handle || "?"));
        const attrs = tweetUrl ? ` href="#" class="open-in-browser" data-url="${escapeAttr(tweetUrl)}"` : "";
        const authorBlock = tweetUrl ? `<a${attrs}>${handleDisplay}</a>` : handleDisplay;
        const tweetLinkBlock = tweetUrl ? `<div class="tweet-link"><a${attrs}>View on X</a></div>` : "";
        return `
    <div class="tweet-card">
      <div class="author">${authorBlock}</div>
      ${tweetLinkBlock}
      <div class="time">${escapeHtml(t.inserted_at || t.posted_at || "")}</div>
      <div class="text">${escapeHtml(t.text || "")}</div>
    </div>
  `;
      }
    )
    .join("");
}

// --- Alerts (desktop notifications for new tweets) ---
const ALERTS_KEYS = { mlb: "alerts-mlb", mlb_all: "alerts-mlb-all", golf: "alerts-golf" };
const STORAGE_ALERTS = { mlb: "ALERTS_MLB", mlb_all: "ALERTS_MLB_ALL", golf: "ALERTS_GOLF" };
const STORAGE_LAST_ID = { mlb: "LAST_TWEET_ID_MLB", mlb_all: "LAST_TWEET_ID_MLB_ALL", golf: "LAST_TWEET_ID_GOLF" };
const ALERTS_POLL_MS = 45000;

function getAlertsEnabled(feedKey) {
  return localStorage.getItem(STORAGE_ALERTS[feedKey]) === "true";
}
function setAlertsEnabled(feedKey, enabled) {
  localStorage.setItem(STORAGE_ALERTS[feedKey], enabled ? "true" : "false");
}
function getLastTweetId(feedKey) {
  return localStorage.getItem(STORAGE_LAST_ID[feedKey]) || null;
}
function setLastTweetId(feedKey, id) {
  if (id != null) localStorage.setItem(STORAGE_LAST_ID[feedKey], String(id));
}

function bindAlertsCheckboxes() {
  Object.entries(ALERTS_KEYS).forEach(([feedKey, id]) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.checked = getAlertsEnabled(feedKey);
    el.addEventListener("change", () => {
      setAlertsEnabled(feedKey, el.checked);
    });
  });
}

async function requestNotificationPermission() {
  const n = window.__TAURI__?.notification;
  if (!n) return false;
  try {
    let ok = await n.isPermissionGranted();
    if (!ok) ok = (await n.requestPermission()) === "granted";
    return !!ok;
  } catch (e) {
    return false;
  }
}

async function showAlertNotification(title, body) {
  const n = window.__TAURI__?.notification;
  if (!n) return;
  try {
    await n.sendNotification({ title, body });
    await invoke("bring_main_window_to_front", {}).catch(() => {});
  } catch (e) {}
}

async function pollAlerts() {
  const feedFetchers = {
    mlb: () => invoke("fetch_recent_tweets", { limit: 1 }),
    mlb_all: () => invoke("fetch_recent_tweets_all", { limit: 1 }),
    golf: () => invoke("fetch_recent_tweets_golf", { limit: 1 }),
  };
  const feedLabels = { mlb: "MLB", mlb_all: "MLB Search All", golf: "Golf" };
  for (const [feedKey, fetchFn] of Object.entries(feedFetchers)) {
    if (!getAlertsEnabled(feedKey)) continue;
    try {
      const tweets = await fetchFn();
      const top = tweets && tweets[0];
      const topId = top && (top.tweet_id || top.id);
      if (topId == null) continue;
      const lastId = getLastTweetId(feedKey);
      if (lastId != null && lastId !== String(topId)) {
        await requestNotificationPermission();
        const author = top.author_handle ? "@" + top.author_handle : "New tweet";
        const text = (top.text || "").substring(0, 80);
        await showAlertNotification(
          feedLabels[feedKey] + " – " + author,
          text ? text + (text.length >= 80 ? "…" : "") : "New tweet"
        );
      }
      setLastTweetId(feedKey, topId);
    } catch (e) {}
  }
}

bindAlertsCheckboxes();
let alertsPollTimer = null;
function startAlertsPolling() {
  if (alertsPollTimer) return;
  alertsPollTimer = setInterval(pollAlerts, ALERTS_POLL_MS);
  pollAlerts();
}
startAlertsPolling();

// --- Kalshi ---
function kalshiEnv() {
  return (kalshiEnvSelect && kalshiEnvSelect.value) || "demo";
}

async function refreshKalshiStatus() {
  if (!kalshiServerStatusEl) return;
  try {
    const up = await invoke("kalshi_server_status");
    kalshiServerStatusEl.textContent = up ? "Running" : "Stopped";
    kalshiServerStatusEl.className = "status-pill " + (up ? "status-on" : "status-off");
    if (btnKalshiServerToggle) btnKalshiServerToggle.textContent = up ? "Stop Kalshi API" : "Start Kalshi API";
  } catch (e) {
    kalshiServerStatusEl.textContent = "Error";
    kalshiServerStatusEl.className = "status-pill status-unknown";
    if (btnKalshiServerToggle) btnKalshiServerToggle.textContent = "Start Kalshi API";
  }
}

async function kalshiRefreshData() {
  const env = kalshiEnv();
  if (kalshiBalanceEl) {
    try {
      const b = await invoke("kalshi_balance", { env });
      const balanceCents = (b && b.balance) != null ? b.balance : null;
      const portfolioCents = (b && b.portfolio_value) != null ? b.portfolio_value : null;
      const balStr = balanceCents != null ? `Balance: $${(balanceCents / 100).toFixed(2)}` : "—";
      const portStr = portfolioCents != null ? `Portfolio: $${(portfolioCents / 100).toFixed(2)}` : "";
      kalshiBalanceEl.textContent = [balStr, portStr].filter(Boolean).join(" · ");
    } catch (e) {
      kalshiBalanceEl.textContent = "Error: " + (e && e.toString());
    }
  }
  if (kalshiExchangeStatusEl) {
    try {
      const s = await invoke("kalshi_exchange_status", { env });
      kalshiExchangeStatusEl.textContent = (s && s.trading_active != null)
        ? (s.trading_active ? "Trading active" : "Trading paused")
        : JSON.stringify(s || "—");
    } catch (e) {
      kalshiExchangeStatusEl.textContent = "Error: " + (e && e.toString());
    }
  }
  try {
    const ordersResp = await invoke("kalshi_orders", { env, limit: 50, status: "resting" });
    const orders = (ordersResp && ordersResp.orders) || [];
    if (kalshiOrdersListEl) {
      if (orders.length === 0) {
        kalshiOrdersListEl.innerHTML = "<p class=\"empty-state\">No resting orders.</p>";
      } else {
        kalshiOrdersListEl.innerHTML = orders.map((o) => {
          const id = escapeHtml(o.order_id || o.id || "?");
          const ticker = escapeHtml(o.ticker || "?");
          const side = escapeHtml((o.side || "yes").toUpperCase());
          const count = o.remaining_count ?? o.count ?? "?";
          const price = o.yes_price ?? o.no_price ?? "?";
          return `<div class="kalshi-order-row">
            <span class="kalshi-order-ticker">${ticker}</span> ${side} ${count} @ ${price}¢
            <button type="button" class="kalshi-cancel-btn secondary" data-order-id="${escapeAttr(String(o.order_id || o.id || ""))}">Cancel</button>
          </div>`;
        }).join("");
        kalshiOrdersListEl.querySelectorAll(".kalshi-cancel-btn").forEach((btn) => {
          btn.addEventListener("click", () => kalshiCancelOrder(btn.dataset.orderId));
        });
      }
    }
  } catch (e) {
    if (kalshiOrdersListEl) kalshiOrdersListEl.innerHTML = "<p class=\"empty-state\">Error: " + escapeHtml(String(e)) + "</p>";
  }
  try {
    const posResp = await invoke("kalshi_positions", { env, limit: 50 });
    const positions = (posResp && posResp.market_positions) || posResp?.positions || [];
    if (kalshiPositionsListEl) {
      if (!positions.length) {
        kalshiPositionsListEl.innerHTML = "<p class=\"empty-state\">No positions.</p>";
      } else {
        kalshiPositionsListEl.innerHTML = positions.map((p) => {
          const ticker = escapeHtml(p.ticker || p.market_ticker || "?");
          const pos = p.position ?? p.contracts ?? "?";
          const cost = p.position_cost != null ? (p.position_cost / 10000).toFixed(2) : "";
          return `<div class="kalshi-position-row"><span class="kalshi-position-ticker">${ticker}</span> position: ${pos}${cost ? " · cost: $" + cost : ""}</div>`;
        }).join("");
      }
    }
  } catch (e) {
    if (kalshiPositionsListEl) kalshiPositionsListEl.innerHTML = "<p class=\"empty-state\">Error: " + escapeHtml(String(e)) + "</p>";
  }
}

async function kalshiCancelOrder(orderId) {
  const env = kalshiEnv();
  try {
    await invoke("kalshi_cancel_order", { env, orderId });
    showToast("Order canceled");
    kalshiRefreshData();
  } catch (e) {
    showToast((e && e.toString()) || "Cancel failed", "error");
  }
}

if (btnKalshiServerToggle) {
  btnKalshiServerToggle.addEventListener("click", async () => {
    try {
      const up = await invoke("kalshi_server_status");
      if (up) await invoke("stop_kalshi_server");
      else await invoke("start_kalshi_server");
      await refreshKalshiStatus();
      if (!up) showToast("Kalshi API started");
    } catch (e) {
      showToast((e && e.toString()) || "Failed", "error");
      refreshKalshiStatus();
    }
  });
}
if (btnKalshiRefresh) btnKalshiRefresh.addEventListener("click", () => kalshiRefreshData());

  const ordersToggle = document.getElementById("kalshi-orders-toggle");
  const positionsToggle = document.getElementById("kalshi-positions-toggle");
  if (ordersToggle) {
    ordersToggle.addEventListener("click", () => {
      const expanded = ordersToggle.getAttribute("aria-expanded") !== "true";
      ordersToggle.setAttribute("aria-expanded", expanded);
    });
  }
  if (positionsToggle) {
    positionsToggle.addEventListener("click", () => {
      const expanded = positionsToggle.getAttribute("aria-expanded") !== "true";
      positionsToggle.setAttribute("aria-expanded", expanded);
    });
  }

  if (kalshiOrderExpiration) {
    kalshiOrderExpiration.addEventListener("change", () => {
      const showDatetime = kalshiOrderExpiration.value === "specific_time";
      if (kalshiOrderExpirationDatetimeWrap) kalshiOrderExpirationDatetimeWrap.style.display = showDatetime ? "" : "none";
      if (showDatetime && kalshiOrderExpirationDatetime) {
        const now = new Date();
        const y = now.getFullYear();
        const m = String(now.getMonth() + 1).padStart(2, "0");
        const d = String(now.getDate()).padStart(2, "0");
        const h = String(now.getHours()).padStart(2, "0");
        const min = String(now.getMinutes()).padStart(2, "0");
        kalshiOrderExpirationDatetime.value = y + "-" + m + "-" + d + "T" + h + ":" + min;
      }
    });
  }

function kalshiUpdateBatchUI() {
  if (!kalshiBatchListEl) return;
  if (kalshiBatchTickers.length === 0) {
    kalshiBatchListEl.textContent = "—";
    if (btnKalshiPlaceBatch) btnKalshiPlaceBatch.disabled = true;
  } else {
    kalshiBatchListEl.textContent = kalshiBatchTickers.join(", ");
    if (btnKalshiPlaceBatch) btnKalshiPlaceBatch.disabled = false;
  }
}

function buildPlaceOrderPayload(orderPayload, side, yesPrice, noPrice, timeInForce, expirationTsParam) {
  const p = { ...orderPayload, side, yesPrice: yesPrice ?? null, noPrice: noPrice ?? null };
  if (expirationTsParam != null && typeof expirationTsParam === "number") {
    p.expirationTs = expirationTsParam;
    delete p.expiration_ts;
    delete p.time_in_force;
    delete p.timeInForce;
  } else if (timeInForce) {
    p.timeInForce = timeInForce;
    delete p.expiration_ts;
    delete p.expirationTs;
    delete p.time_in_force;
  }
  return p;
}

if (formKalshiOrder) {
  formKalshiOrder.addEventListener("submit", async (e) => {
    e.preventDefault();
    const ticker = kalshiOrderTicker && kalshiOrderTicker.value.trim();
    const count = parseInt(kalshiOrderCount && kalshiOrderCount.value, 10) || 1;
    const sides = (kalshiOrderSides && kalshiOrderSides.value) || "yes";
    const yesPriceVal = kalshiOrderYesPrice && kalshiOrderYesPrice.value.trim();
    const noPriceVal = kalshiOrderNoPrice && kalshiOrderNoPrice.value.trim();
    const yesPrice = yesPriceVal ? parseInt(yesPriceVal, 10) : null;
    const noPrice = noPriceVal ? parseInt(noPriceVal, 10) : null;
    const env = kalshiEnv();
    const expirationType = (kalshiOrderExpiration && kalshiOrderExpiration.value) || "good_till_canceled";
    let expirationTs = null;
    if (expirationType === "specific_time") {
      const inputEl = kalshiOrderExpirationDatetime;
      if (!inputEl || !inputEl.value || !String(inputEl.value).trim()) {
        showToast("Request aborted: expiration at specific time is required but not set.", "error");
        return;
      }
      const ts = Math.floor(new Date(inputEl.value).getTime() / 1000);
      if (Number.isNaN(ts) || ts <= 0) {
        showToast("Request aborted: expiration at specific time is required but not valid.", "error");
        return;
      }
      if (ts <= Math.floor(Date.now() / 1000)) {
        showToast("Request aborted: expiration must be in the future.", "error");
        return;
      }
      expirationTs = ts;
    }
    if (!ticker) {
      showToast("Enter a ticker", "error");
      return;
    }
    const timeInForce = expirationType === "good_till_canceled" ? "good_till_canceled" : null;
    const expirationTsParam = expirationType !== "good_till_canceled" && expirationTs != null ? expirationTs : null;
    if (expirationType === "specific_time") {
      const hasValid = expirationTsParam != null && typeof expirationTsParam === "number" && !Number.isNaN(expirationTsParam) && expirationTsParam > Math.floor(Date.now() / 1000);
      if (!hasValid) {
        showToast("Request aborted: expiration at specific time is required but not valid or not set.", "error");
        return;
      }
    }
    const basePayload = { env, ticker, action: "buy", count, yesPrice: null, noPrice: null };
    if (expirationType === "good_till_canceled") basePayload.timeInForce = "good_till_canceled";
    else if (expirationTsParam != null) basePayload.expirationTs = expirationTsParam;
    const orderPayload = basePayload;
    try {
      if (sides === "both") {
        if (yesPrice == null || noPrice == null) {
          showToast("Set both Yes (¢) and No (¢) for Both sides", "error");
          return;
        }
        const payloadYes = buildPlaceOrderPayload(orderPayload, "yes", yesPrice, null, timeInForce, expirationTsParam);
        const payloadNo = buildPlaceOrderPayload(orderPayload, "no", null, noPrice, timeInForce, expirationTsParam);
        await invoke("kalshi_place_order", payloadYes);
        await invoke("kalshi_place_order", payloadNo);
        showToast("Both orders placed");
      } else {
        const price = sides === "yes" ? yesPrice : noPrice;
        if (price == null) {
          showToast("Set price for " + (sides === "yes" ? "Yes" : "No"), "error");
          return;
        }
        const payload = buildPlaceOrderPayload(orderPayload, sides, sides === "yes" ? price : null, sides === "no" ? price : null, timeInForce, expirationTsParam);
        await invoke("kalshi_place_order", payload);
        const useReciprocal = kalshiOrderReciprocal && kalshiOrderReciprocal.checked;
        if (useReciprocal) {
          try {
            const rec = await invoke("kalshi_market_reciprocal", { env, ticker });
            const reciprocalTicker = rec && rec.reciprocal_ticker;
            if (reciprocalTicker) {
              const oppositeSide = sides === "yes" ? "no" : "yes";
              const reciprocalPayload = buildPlaceOrderPayload(
                { ...orderPayload, ticker: reciprocalTicker },
                oppositeSide,
                oppositeSide === "yes" ? price : null,
                oppositeSide === "no" ? price : null,
                timeInForce,
                expirationTsParam
              );
              await invoke("kalshi_place_order", reciprocalPayload);
              showToast("2 orders placed (main + reciprocal)");
            } else {
              showToast("Order placed (no reciprocal market)");
            }
          } catch (_) {
            showToast("Order placed (reciprocal not available)", "success");
          }
        } else {
          showToast("Order placed");
        }
      }
      kalshiRefreshData();
    } catch (err) {
      showToast((err && err.toString()) || "Place order failed", "error");
    }
  });
}

if (btnKalshiClearBatch) {
  btnKalshiClearBatch.addEventListener("click", () => {
    kalshiBatchTickers = [];
    kalshiUpdateBatchUI();
  });
}

if (btnKalshiPlaceBatch) {
  btnKalshiPlaceBatch.addEventListener("click", async () => {
    if (kalshiBatchTickers.length === 0) return;
    const sides = (kalshiOrderSides && kalshiOrderSides.value) || "yes";
    const count = parseInt(kalshiOrderCount && kalshiOrderCount.value, 10) || 1;
    const yesPriceVal = kalshiOrderYesPrice && kalshiOrderYesPrice.value.trim();
    const noPriceVal = kalshiOrderNoPrice && kalshiOrderNoPrice.value.trim();
    const yesPrice = yesPriceVal ? parseInt(yesPriceVal, 10) : null;
    const noPrice = noPriceVal ? parseInt(noPriceVal, 10) : null;
    const expirationType = (kalshiOrderExpiration && kalshiOrderExpiration.value) || "good_till_canceled";
    let expirationTs = null;
    if (expirationType === "specific_time" && kalshiOrderExpirationDatetime && kalshiOrderExpirationDatetime.value) {
      expirationTs = Math.floor(new Date(kalshiOrderExpirationDatetime.value).getTime() / 1000);
    }
    const extra = {};
    if (expirationType === "good_till_canceled") extra.time_in_force = "good_till_canceled";
    else if (expirationTs != null) extra.expiration_ts = expirationTs;
    const orders = [];
    const maxOrders = 10;
    for (const ticker of kalshiBatchTickers) {
      if (orders.length >= maxOrders) break;
      if (sides === "both") {
        if (yesPrice != null) orders.push({ ticker, side: "yes", count, yes_price: yesPrice, ...extra });
        if (orders.length < maxOrders && noPrice != null) orders.push({ ticker, side: "no", count, no_price: noPrice, ...extra });
      } else {
        const price = sides === "yes" ? yesPrice : noPrice;
        if (price != null) orders.push({ ticker, side: sides, count, yes_price: sides === "yes" ? price : null, no_price: sides === "no" ? price : null, ...extra });
      }
    }
    if (orders.length === 0) {
      showToast("Set price(s) for batch", "error");
      return;
    }
    const env = kalshiEnv();
    try {
      const result = await invoke("kalshi_batch_place_orders", { env, orders });
      const placed = (result && result.placed && result.placed.length) || 0;
      const errs = (result && result.errors && result.errors.length) || 0;
      showToast(placed + " placed" + (errs ? ", " + errs + " errors" : ""));
      kalshiBatchTickers = [];
      kalshiUpdateBatchUI();
      kalshiRefreshData();
    } catch (err) {
      showToast((err && err.toString()) || "Batch place failed", "error");
    }
  });
}

if (btnKalshiLoadMarkets) {
  btnKalshiLoadMarkets.addEventListener("click", async () => {
    const eventTicker = (kalshiEventTicker && kalshiEventTicker.value.trim()) || null;
    const statusRaw = kalshiMarketsStatus ? kalshiMarketsStatus.value : "";
    const status = statusRaw.trim() || undefined;
    const env = kalshiEnv();
    if (!kalshiMarketsListEl) return;
    try {
      const hasDash = eventTicker && eventTicker.includes("-");
      const dashCount = eventTicker ? (eventTicker.match(new RegExp("-", "g")) || []).length : 0;
      const eventTickerForApi = hasDash
        ? (dashCount >= 2 ? eventTicker.replace(new RegExp("-[^-]*$"), "") : eventTicker)
        : null;
      const seriesTickerForApi = eventTicker && !hasDash ? eventTicker : undefined;
      const tickersForApi = hasDash && dashCount >= 2 ? eventTicker : undefined;
      const payload = {
        env,
        limit: 200,
        status: status || null,
        event_ticker: eventTickerForApi || null,
        series_ticker: seriesTickerForApi || null,
        tickers: tickersForApi || null,
      };
      const data = await invoke("kalshi_markets", { p: payload });
      // Diagnostic: see what we actually received (keys and markets count)
      try {
        var keys = data ? Object.keys(data) : [];
        var marketsCount = (data && data.markets) ? data.markets.length : (data && Array.isArray(data.markets) ? data.markets.length : "no .markets");
        console.log("[Kalshi Load] response keys:", keys, "markets count:", marketsCount);
      } catch (_) {}
      if (kalshiMarketsRequestUrlEl) kalshiMarketsRequestUrlEl.textContent = data && data.request_url ? "Request URL: " + data.request_url : "";
      // Accept top-level .markets or wrapped .data.markets (so we don't lose data if shape differs)
      let markets = (data && data.markets) || (data && data.data && data.data.markets) || [];
      // Only filter client-side when we did a generic fetch (no series/event/tickers param). Otherwise the API already returned the right set.
      const apiWasTargeted = seriesTickerForApi || eventTickerForApi || tickersForApi;
      if (eventTicker && !apiWasTargeted) {
        const q = eventTicker.toLowerCase();
        const qPrefix = eventTickerForApi && eventTickerForApi !== eventTicker ? eventTickerForApi.toLowerCase() : null;
        markets = markets.filter((m) => {
          const et = (m.event_ticker || "").toLowerCase();
          const tk = (m.ticker || "").toLowerCase();
          return et === q || tk === q || et.startsWith(q) || tk.startsWith(q) ||
            (qPrefix && (et === qPrefix || et.startsWith(qPrefix) || tk.startsWith(qPrefix)));
        });
      }
      if (kalshiMarketsSort && kalshiMarketsSort.value) {
        const mode = kalshiMarketsSort.value;
        if (mode === "alpha") {
          markets = markets.slice().sort((a, b) => {
            const ta = (a.title || a.ticker || "").toLowerCase();
            const tb = (b.title || b.ticker || "").toLowerCase();
            if (ta < tb) return -1;
            if (ta > tb) return 1;
            return 0;
          });
        } else if (mode === "expiry") {
          markets = markets.slice().sort((a, b) => {
            const da = a.close_time ? Date.parse(a.close_time) : Infinity;
            const db = b.close_time ? Date.parse(b.close_time) : Infinity;
            return da - db;
          });
        }
      }
      if (markets.length === 0) {
        const hint = eventTicker
          ? "No markets matched. Try status \"Any\" for closed/settled (e.g. Maine 94th HD). Series: KXMAINE94, Event: KXMAINE94-26, Market: KXMAINE94-26-SHAR."
          : "Enter a Series, Event, or Market ticker and click Load strikes.";
        kalshiMarketsListEl.innerHTML = "<p class=\"empty-state\">" + escapeHtml(hint) + "</p>";
      } else {
        kalshiMarketsListEl.innerHTML = markets.map((m) => {
          const ticker = m.ticker || "?";
          const fullTitle = m.title || "";
          const truncatedTitle = fullTitle.length > 55 ? fullTitle.substring(0, 55) + "…" : fullTitle;
          const titleHtml = escapeHtml(truncatedTitle);
          const fullTitleHtml = escapeHtml(fullTitle);
          return `<div class="kalshi-market-row">
            <span class="kalshi-market-ticker" data-ticker="${escapeAttr(ticker)}" title="Set as single ticker">${escapeHtml(ticker)}</span>
            <span class="kalshi-market-title" title="Click to show full title">${titleHtml}</span>
            <button type="button" class="kalshi-add-to-order-btn secondary" data-ticker="${escapeAttr(ticker)}">Add to order</button>
            <div class="kalshi-market-title-full" aria-hidden="true">${fullTitleHtml}</div>
          </div>`;
        }).join("");
        kalshiMarketsListEl.querySelectorAll(".kalshi-market-ticker").forEach((el) => {
          el.addEventListener("click", () => {
            if (kalshiOrderTicker) kalshiOrderTicker.value = el.dataset.ticker || "";
          });
        });
        kalshiMarketsListEl.querySelectorAll(".kalshi-market-title").forEach((el) => {
          el.addEventListener("click", () => {
            const row = el.closest(".kalshi-market-row");
            if (row) row.classList.toggle("kalshi-market-row--expanded");
          });
        });
        kalshiMarketsListEl.querySelectorAll(".kalshi-add-to-order-btn").forEach((btn) => {
          btn.addEventListener("click", () => {
            const t = btn.dataset.ticker;
            if (!t) return;
            if (kalshiOrderTicker) kalshiOrderTicker.value = t;
            if (!kalshiBatchTickers.includes(t)) {
              kalshiBatchTickers.push(t);
              if (kalshiBatchTickers.length > 10) kalshiBatchTickers = kalshiBatchTickers.slice(-10);
              kalshiUpdateBatchUI();
            }
            showToast("Added " + t);
          });
        });
      }
    } catch (e) {
      const msg = (e && (e.message || e.toString())) || "Request failed";
      if (kalshiMarketsRequestUrlEl) kalshiMarketsRequestUrlEl.textContent = "";
      if (kalshiMarketsListEl) kalshiMarketsListEl.innerHTML = "<p class=\"empty-state\">Error: " + escapeHtml(msg) + ". Is the Kalshi API server running (Start Kalshi API above)?</p>";
    }
  });
}

loadMonitors();
loadTablesDropdown();
// No auto-check of tweets server; status is "Server: Unknown" until user clicks Start/Stop server
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}
