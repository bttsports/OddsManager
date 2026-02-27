//! OddsManager desktop – Rust backend.
//!
//! Provides commands for managing X (Twitter) list monitors: store configs,
//! parse list URLs, generate Tampermonkey scripts (DB only), and run the Playwright list monitor.

use serde::{Deserialize, Serialize};
use std::fs;
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::{Emitter, Manager, State};
use tauri_plugin_dialog::DialogExt;

/// Tracks the tweets API server process (python news/tweets_api.py) started by the app.
struct ServerProcess(Mutex<Option<Child>>);

/// Tracks the Kalshi API server process (python betting_outs/kalshi/kalshi_api.py) started by the app.
struct KalshiServerProcess(Mutex<Option<Child>>);

/// Payload for kalshi_markets: query params for GET /markets (series_ticker, event_ticker, tickers, etc.).
#[derive(Debug, Default, Deserialize)]
#[serde(rename_all = "snake_case")]
struct KalshiMarketsParams {
    env: Option<String>,
    limit: Option<u32>,
    cursor: Option<String>,
    status: Option<String>,
    event_ticker: Option<String>,
    series_ticker: Option<String>,
    tickers: Option<String>,
}

/// One saved monitor: list URL and keywords to watch.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Monitor {
    pub id: String,
    pub name: String,
    pub list_url: String,
    pub keywords: Vec<String>,
    /// Optional: refresh interval in minutes (for generated script).
    #[serde(default = "default_refresh_minutes")]
    pub refresh_minutes: u32,
    /// Which feed/table the generated script POSTs to: "mlb" -> /api/tweet, "golf" -> /api/tweet/golf, etc.
    #[serde(default)]
    pub feed: String,
}

fn default_refresh_minutes() -> u32 {
    1
}

/// Normalize feed field to table name (backward compat: "mlb"/"golf" -> "mlb_tweets"/"golf_tweets").
fn feed_to_table_name(feed: &str) -> String {
    let s = feed.trim().to_lowercase();
    match s.as_str() {
        "mlb" => "mlb_tweets".to_string(),
        "golf" => "golf_tweets".to_string(),
        _ if s.ends_with("_tweets") => s,
        _ if !s.is_empty() => format!("{}_tweets", s),
        _ => "mlb_tweets".to_string(),
    }
}

/// API path for POSTing tweets (keyword script). Uses generic /api/tweet/into/<table_name>.
fn tweet_api_path_for_feed(feed: &str) -> String {
    let table = feed_to_table_name(feed);
    format!("/api/tweet/into/{}", table)
}

/// Path to the JSON file where we store monitors (in app data dir).
fn monitors_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?;
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("monitors.json"))
}

/// Write a single monitor to project news/monitors/{id}.json (for local backup / scripts).
fn save_monitor_to_news_folder(monitor: &Monitor) -> Result<(), String> {
    let root = project_root()?;
    let dir = root.join("news").join("monitors");
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join(format!("{}.json", monitor.id));
    fs::write(
        &path,
        serde_json::to_string_pretty(monitor).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

/// Remove news/monitors/{id}.json when a monitor is deleted.
fn remove_monitor_from_news_folder(id: &str) {
    if let Ok(root) = project_root() {
        let path = root.join("news").join("monitors").join(format!("{}.json", id));
        let _ = fs::remove_file(&path);
    }
}

/// Parse X/Twitter list URL to extract list id (numeric or slug).
/// Supports: https://x.com/i/lists/52021139, https://twitter.com/i/lists/52021139,
/// and https://x.com/username/lists/12345 style URLs.
pub fn parse_list_id_from_url(url: &str) -> Option<String> {
    let url = url.trim();
    if url.is_empty() {
        return None;
    }
    // After split('/').filter: ["https:", "x.com", "i", "lists", "52021139"] or ["https:", "x.com", "user", "lists", "123"]
    let segments: Vec<&str> = url.split('/').filter(|s| !s.is_empty()).collect();
    if segments.len() >= 5 {
        // host, "i", "lists", id
        if segments.get(2).copied() == Some("i") && segments.get(3).copied() == Some("lists") {
            return Some(segments[4].to_string());
        }
        // host, username, "lists", id
        if segments.get(3).copied() == Some("lists") {
            return Some(segments[4].to_string());
        }
    }
    if segments.len() == 4 && segments.get(2).copied() == Some("lists") {
        return Some(segments[3].to_string());
    }
    None
}

/// Config written to news/monitor_config.json for run_list_monitor.py.
fn monitor_config_json(monitor: &Monitor) -> serde_json::Value {
    let list_id = parse_list_id_from_url(&monitor.list_url).unwrap_or_else(|| "default".to_string());
    serde_json::json!({
        "list_url": monitor.list_url,
        "list_id": list_id,
        "keywords": monitor.keywords,
        "catch_up_threshold_minutes": 5,
        "max_cache_size": 200
    })
}

/// Write monitor config to project news/monitor_config.json and return run instructions.
pub fn write_list_monitor_config_and_instructions(monitor: &Monitor, root: &std::path::Path) -> Result<String, String> {
    let config_path = root.join("news").join("monitor_config.json");
    let json = monitor_config_json(monitor);
    if let Some(parent) = config_path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    fs::write(
        &config_path,
        serde_json::to_string_pretty(&json).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    Ok(format!(
        "Config saved to news/monitor_config.json\n\nFrom project root run:\n  python news/run_list_monitor.py --config news/monitor_config.json\n\nOr use news/start_list_monitor.bat. To run at logon: powershell -ExecutionPolicy Bypass -File news/install_list_monitor_task.ps1"
    ))
}

/// Build exact list URL match lines for @match (x.com and twitter.com) so the script only runs on this list.
fn list_match_urls(list_url: &str) -> (String, String) {
    let u = list_url.trim();
    let x = if u.contains("twitter.com") {
        u.replace("https://twitter.com", "https://x.com")
            .replace("http://twitter.com", "https://x.com")
    } else {
        u.to_string()
    };
    let tw = if u.contains("x.com") {
        u.replace("https://x.com", "https://twitter.com")
            .replace("http://x.com", "https://twitter.com")
    } else {
        u.to_string()
    };
    (x, tw)
}

/// Generate the full Tampermonkey script for this monitor (DB only, no desktop notifications; includes @connect for localhost).
fn generate_tampermonkey_script(monitor: &Monitor) -> String {
    let list_id = parse_list_id_from_url(&monitor.list_url).unwrap_or_else(|| "LIST_ID".to_string());
    let (match_x, match_twitter) = list_match_urls(&monitor.list_url);
    let keywords_js: String = monitor
        .keywords
        .iter()
        .map(|k| format!("{:?}", k))
        .collect::<Vec<_>>()
        .join(", ");
    let name_escaped = monitor.name.replace('\\', "\\\\").replace('"', "\\\"");
    let version = chrono::Utc::now().format("%Y.%m.%d");
    format!(
        r#"// ==UserScript==
// @name         X List Monitor: {}
// @namespace    http://tampermonkey.net/
// @version      {}
// @description  X list keyword monitor – sends matching tweets to local API (no desktop notifications)
// @match        {}
// @match        {}
// @grant        GM_xmlhttpRequest
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-end
// ==/UserScript==

(function() {{
    'use strict';

    const API_URL = "http://localhost:8765";
    const API_TWEET_PATH = "{}";
    const KEYWORDS = [{}];
    const LIST_ID = "{}";
    const REFRESH_MINUTES = {};
    const CATCH_UP_THRESHOLD_MINUTES = 5;
    const STORAGE_KEY = "X_MONITOR_SEEN_CACHE_" + LIST_ID;
    const STATE_KEY = "X_MONITOR_STATE_" + LIST_ID;
    const MAX_CACHE_SIZE = 200;
    const SCROLL_STEP_PX = 800;
    const SCROLL_WAIT_MS = 1800;
    const MAX_SCROLL_STEPS = 50;
    const INITIAL_WAIT_BEFORE_SCROLL_MS = 2000;

    function getVisibleTweetIds() {{
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        const ids = new Set();
        articles.forEach((a) => {{
            const id = getTweetIdFromArticle(a);
            if (id) ids.add(id);
        }});
        return ids;
    }}

    function scrollUntilLastSeen() {{
        return new Promise((resolve) => {{
            const state = getState();
            const lastId = state.lastTweetId;
            if (!lastId) {{
                let count = 0;
                function doScroll() {{
                    window.scrollBy(0, SCROLL_STEP_PX);
                    count++;
                    if (count >= 6) resolve();
                    else setTimeout(doScroll, SCROLL_WAIT_MS);
                }}
                setTimeout(doScroll, SCROLL_WAIT_MS);
                return;
            }}
            let scrollCount = 0;
            let lastScrollHeight = 0;
            function step() {{
                const ids = getVisibleTweetIds();
                if (ids.has(lastId) || scrollCount >= MAX_SCROLL_STEPS) {{ resolve(); return; }}
                const sh = document.documentElement.scrollHeight;
                if (sh === lastScrollHeight && scrollCount > 4) {{ resolve(); return; }}
                lastScrollHeight = sh;
                window.scrollBy(0, SCROLL_STEP_PX);
                scrollCount++;
                setTimeout(step, SCROLL_WAIT_MS);
            }}
            setTimeout(step, SCROLL_WAIT_MS);
        }});
    }}

    console.log("🚀 Monitor Starting (DB)...");

    function getSeenCache() {{
        const data = localStorage.getItem(STORAGE_KEY);
        return data ? JSON.parse(data) : [];
    }}

    function saveToCache(fingerprint) {{
        let cache = getSeenCache();
        if (!cache.includes(fingerprint)) {{
            cache.push(fingerprint);
            if (cache.length > MAX_CACHE_SIZE) cache = cache.slice(-MAX_CACHE_SIZE);
            localStorage.setItem(STORAGE_KEY, JSON.stringify(cache));
        }}
    }}

    function getState() {{
        const data = localStorage.getItem(STATE_KEY);
        return data ? JSON.parse(data) : {{ lastRunTime: 0, lastTweetId: null, lastTweetTime: null }};
    }}

    function saveState(lastRunTime, lastTweetId, lastTweetTime) {{
        const s = getState();
        localStorage.setItem(STATE_KEY, JSON.stringify({{
            lastRunTime: lastRunTime !== undefined ? lastRunTime : s.lastRunTime,
            lastTweetId: lastTweetId !== undefined ? lastTweetId : s.lastTweetId,
            lastTweetTime: lastTweetTime !== undefined ? lastTweetTime : s.lastTweetTime
        }}));
    }}

    function getTweetIdFromArticle(article) {{
        const linkEl = article.querySelector('time')?.closest('a');
        if (!linkEl || !linkEl.href) return null;
        const m = linkEl.href.match(/\/status\/(\d+)/);
        return m ? m[1] : null;
    }}

    function getTweetTimeFromArticle(article) {{
        const timeEl = article.querySelector('time');
        return timeEl ? timeEl.getAttribute('datetime') : null;
    }}

    function getAuthorFromArticle(article) {{
        const authorLink = article.querySelector('a[href^="/"]');
        if (authorLink && authorLink.href) {{
            const m = authorLink.href.match(/^https?:\/\/[^/]+\/([^/]+)/);
            if (m) return m[1];
        }}
        return "unknown";
    }}

    function escapeRegex(s) {{
        return s.replace(/[.*+?^${{}}()|[\]\\]/g, '\\$&');
    }}

    function hasWholeWordMatch(text, keywords) {{
        for (const kw of keywords) {{
            const re = new RegExp('\\b' + escapeRegex(kw) + '\\b', 'i');
            if (re.test(text)) return true;
        }}
        return false;
    }}

    function sendToApi(tweetId, authorHandle, text, url, postedAt) {{
        GM_xmlhttpRequest({{ method: "POST", url: API_URL + API_TWEET_PATH, headers: {{ "Content-Type": "application/json" }}, data: JSON.stringify({{ tweet_id: tweetId, author_handle: authorHandle, text: text, url: url || null, posted_at: postedAt || null }}), onload: function(res) {{ if (res.status >= 200 && res.status < 300) console.log("%c📤 Sent to DB: " + authorHandle, "color: #00ba7c;"); else console.warn("API " + res.status); }}, onerror: function() {{ console.warn("API failed (run python news/tweets_api.py)"); }} }});
    }}

    function processMatch(article, text, tweetUrl, tweetId, tweetTime) {{
        const cache = getSeenCache();
        const fingerprint = text.substring(0, 120);
        if (cache.includes(fingerprint)) return;
        if (!hasWholeWordMatch(text, KEYWORDS)) return;
        const author = getAuthorFromArticle(article);
        const id = tweetId || getTweetIdFromArticle(article);
        const time = tweetTime || getTweetTimeFromArticle(article);
        sendToApi(id || String(Date.now()), author, text, tweetUrl, time);
        saveToCache(fingerprint);
        saveState(Date.now(), id, time);
    }}

    function scan() {{
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        articles.forEach(article => {{
            const textEl = article.querySelector('[data-testid="tweetText"]');
            if (!textEl) return;
            const text = textEl.innerText;
            const linkEl = article.querySelector('time')?.closest('a');
            const tweetUrl = linkEl ? linkEl.href : null;
            processMatch(article, text, tweetUrl, getTweetIdFromArticle(article), getTweetTimeFromArticle(article));
        }});
        saveState(Date.now());
    }}

    function catchUpScan() {{
        const state = getState();
        const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
        const items = [];
        articles.forEach(article => {{
            const textEl = article.querySelector('[data-testid="tweetText"]');
            if (!textEl) return;
            const text = textEl.innerText;
            const linkEl = article.querySelector('time')?.closest('a');
            const tweetUrl = linkEl ? linkEl.href : null;
            items.push({{ article, text, tweetUrl, tweetId: getTweetIdFromArticle(article), tweetTime: getTweetTimeFromArticle(article) }});
        }});
        items.sort((a, b) => (b.tweetTime || '').localeCompare(a.tweetTime || ''));
        for (const item of items) {{
            if (state.lastTweetId && item.tweetId === state.lastTweetId) break;
            if (state.lastTweetTime && item.tweetTime && item.tweetTime <= state.lastTweetTime) break;
            processMatch(item.article, item.text, item.tweetUrl, item.tweetId, item.tweetTime);
        }}
        saveState(Date.now());
    }}

    function maybeCatchUpThenScan() {{
        const state = getState();
        const gap = (Date.now() - state.lastRunTime) / (60 * 1000);
        if (gap >= CATCH_UP_THRESHOLD_MINUTES) catchUpScan();
        else scan();
    }}

    let scanTimer = null;
    const observer = new MutationObserver(() => {{
        if (scanTimer) clearTimeout(scanTimer);
        scanTimer = setTimeout(() => {{
            scanTimer = null;
            const state = getState();
            const gapMin = (Date.now() - state.lastRunTime) / (60 * 1000);
            if (gapMin >= CATCH_UP_THRESHOLD_MINUTES) catchUpScan();
            else scan();
        }}, 400);
    }});
    function attachObserver() {{
        const target = document.body;
        if (!target || !(target instanceof Node)) return false;
        observer.observe(target, {{ childList: true, subtree: true }});
        maybeCatchUpThenScan();
        setTimeout(() => {{
            scrollUntilLastSeen().then(() => {{
                catchUpScan();
                setTimeout(() => {{ window.location.reload(); }}, REFRESH_MINUTES * 60 * 1000);
            }});
        }}, INITIAL_WAIT_BEFORE_SCROLL_MS);
        return true;
    }}
    if (!attachObserver()) {{
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', () => attachObserver());
        }} else {{
            const check = () => {{ if (!attachObserver()) setTimeout(check, 50); }};
            setTimeout(check, 0);
        }}
    }}
}})();
"#,
        name_escaped,
        version,
        match_x,
        match_twitter,
        tweet_api_path_for_feed(&monitor.feed),
        keywords_js,
        list_id,
        monitor.refresh_minutes
    )
}

#[tauri::command]
fn list_monitors(app: tauri::AppHandle) -> Result<Vec<Monitor>, String> {
    let path = monitors_path(&app)?;
    if !path.exists() {
        return Ok(vec![]);
    }
    let s = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let list: Vec<Monitor> = serde_json::from_str(&s).unwrap_or_default();
    Ok(list)
}

#[tauri::command]
fn add_monitor(
    app: tauri::AppHandle,
    name: String,
    list_url: String,
    keywords: Vec<String>,
    refresh_minutes: Option<u32>,
    feed: Option<String>,
) -> Result<Monitor, String> {
    let mut list = list_monitors(app.clone())?;
    let id = uuid::Uuid::new_v4().to_string();
    let feed_val = feed
        .map(|s| s.trim().to_lowercase())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "mlb".to_string());
    let monitor = Monitor {
        id: id.clone(),
        name: name.trim().to_string(),
        list_url: list_url.trim().to_string(),
        keywords: keywords
            .into_iter()
            .map(|k| k.trim().to_string())
            .filter(|k| !k.is_empty())
            .collect(),
        refresh_minutes: refresh_minutes.unwrap_or(1),
        feed: feed_val,
    };
    list.push(monitor.clone());
    let path = monitors_path(&app)?;
    fs::write(
        &path,
        serde_json::to_string_pretty(&list).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    let _ = save_monitor_to_news_folder(&monitor);
    Ok(monitor)
}

#[tauri::command]
fn delete_monitor(app: tauri::AppHandle, id: String) -> Result<(), String> {
    let mut list = list_monitors(app.clone())?;
    list.retain(|m| m.id != id);
    let path = monitors_path(&app)?;
    fs::write(
        &path,
        serde_json::to_string_pretty(&list).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    remove_monitor_from_news_folder(&id);
    Ok(())
}

#[tauri::command]
fn generate_script(monitor: Monitor) -> Result<String, String> {
    Ok(generate_tampermonkey_script(&monitor))
}

/// Generate Tampermonkey script that scrapes all tweets (no keyword filter), POSTs to /api/tweet/all.
fn generate_tampermonkey_script_scrape_all(monitor: &Monitor) -> String {
    let list_id = parse_list_id_from_url(&monitor.list_url).unwrap_or_else(|| "LIST_ID".to_string());
    let (match_x, match_twitter) = list_match_urls(&monitor.list_url);
    let name_escaped = monitor.name.replace('\\', "\\\\").replace('"', "\\\"");
    let version = chrono::Utc::now().format("%Y.%m.%d");
    format!(
        r#"// ==UserScript==
// @name         X List Monitor: {} – Scrape All
// @namespace    http://tampermonkey.net/
// @version      {}
// @description  Same list; scrapes all tweets (no keyword filter). POSTs to /api/tweet/all.
// @match        {}
// @match        {}
// @grant        GM_xmlhttpRequest
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-end
// ==/UserScript==

(function() {{
    'use strict';

    const API_URL = "http://localhost:8765";
    const LIST_ID = "{}";
    const REFRESH_MINUTES = {};
    const CATCH_UP_THRESHOLD_MINUTES = 5;
    const STORAGE_KEY = "X_MONITOR_SEEN_CACHE_" + LIST_ID + "_ScrapeAll";
    const STATE_KEY = "X_MONITOR_STATE_" + LIST_ID + "_ScrapeAll";
    const MAX_CACHE_SIZE = 200;
    const SCROLL_STEP_PX = 800;
    const SCROLL_WAIT_MS = 1800;
    const MAX_SCROLL_STEPS = 50;
    const INITIAL_WAIT_BEFORE_SCROLL_MS = 2000;

    function getVisibleTweetIds() {{
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        const ids = new Set();
        articles.forEach((a) => {{
            const id = getTweetIdFromArticle(a);
            if (id) ids.add(id);
        }});
        return ids;
    }}

    function scrollUntilLastSeen() {{
        return new Promise((resolve) => {{
            const state = getState();
            const lastId = state.lastTweetId;
            if (!lastId) {{
                let count = 0;
                function doScroll() {{
                    window.scrollBy(0, SCROLL_STEP_PX);
                    count++;
                    if (count >= 6) resolve();
                    else setTimeout(doScroll, SCROLL_WAIT_MS);
                }}
                setTimeout(doScroll, SCROLL_WAIT_MS);
                return;
            }}
            let scrollCount = 0;
            let lastScrollHeight = 0;
            function step() {{
                const ids = getVisibleTweetIds();
                if (ids.has(lastId) || scrollCount >= MAX_SCROLL_STEPS) {{ resolve(); return; }}
                const sh = document.documentElement.scrollHeight;
                if (sh === lastScrollHeight && scrollCount > 4) {{ resolve(); return; }}
                lastScrollHeight = sh;
                window.scrollBy(0, SCROLL_STEP_PX);
                scrollCount++;
                setTimeout(step, SCROLL_WAIT_MS);
            }}
            setTimeout(step, SCROLL_WAIT_MS);
        }});
    }}

    console.log("🚀 Scrape-All monitor starting (no keyword filter)...");

    function getSeenCache() {{
        const data = localStorage.getItem(STORAGE_KEY);
        return data ? JSON.parse(data) : [];
    }}

    function saveToCache(fingerprint) {{
        let cache = getSeenCache();
        if (!cache.includes(fingerprint)) {{
            cache.push(fingerprint);
            if (cache.length > MAX_CACHE_SIZE) cache = cache.slice(-MAX_CACHE_SIZE);
            localStorage.setItem(STORAGE_KEY, JSON.stringify(cache));
        }}
    }}

    function getState() {{
        const data = localStorage.getItem(STATE_KEY);
        return data ? JSON.parse(data) : {{ lastRunTime: 0, lastTweetId: null, lastTweetTime: null }};
    }}

    function saveState(lastRunTime, lastTweetId, lastTweetTime) {{
        const s = getState();
        localStorage.setItem(STATE_KEY, JSON.stringify({{
            lastRunTime: lastRunTime !== undefined ? lastRunTime : s.lastRunTime,
            lastTweetId: lastTweetId !== undefined ? lastTweetId : s.lastTweetId,
            lastTweetTime: lastTweetTime !== undefined ? lastTweetTime : s.lastTweetTime
        }}));
    }}

    function getTweetIdFromArticle(article) {{
        const linkEl = article.querySelector('time')?.closest('a');
        if (!linkEl || !linkEl.href) return null;
        const m = linkEl.href.match(/\/status\/(\d+)/);
        return m ? m[1] : null;
    }}

    function getTweetTimeFromArticle(article) {{
        const timeEl = article.querySelector('time');
        return timeEl ? timeEl.getAttribute('datetime') : null;
    }}

    function getAuthorFromArticle(article) {{
        const authorLink = article.querySelector('a[href^="/"]');
        if (authorLink && authorLink.href) {{
            const m = authorLink.href.match(/^https?:\\/\\/[^/]+\\/([^/]+)/);
            if (m) return m[1];
        }}
        return "unknown";
    }}

    function sendToApi(tweetId, authorHandle, text, url, postedAt) {{
        GM_xmlhttpRequest({{ method: "POST", url: API_URL + "/api/tweet/all", headers: {{ "Content-Type": "application/json" }}, data: JSON.stringify({{ tweet_id: tweetId, author_handle: authorHandle, text: text, url: url || null, posted_at: postedAt || null }}), onload: function(res) {{ if (res.status >= 200 && res.status < 300) console.log("%c📤 Sent (scrape-all): " + authorHandle, "color: #00ba7c;"); else console.warn("API " + res.status); }}, onerror: function() {{ console.warn("API failed (run python news/tweets_api.py)"); }} }});
    }}

    function processTweet(article, text, tweetUrl, tweetId, tweetTime) {{
        const cache = getSeenCache();
        const fingerprint = text.substring(0, 120);
        if (cache.includes(fingerprint)) return;
        const author = getAuthorFromArticle(article);
        const id = tweetId || getTweetIdFromArticle(article);
        const time = tweetTime || getTweetTimeFromArticle(article);
        sendToApi(id || String(Date.now()), author, text, tweetUrl, time);
        saveToCache(fingerprint);
        saveState(Date.now(), id, time);
    }}

    function scan() {{
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        articles.forEach(article => {{
            const textEl = article.querySelector('[data-testid="tweetText"]');
            if (!textEl) return;
            const text = textEl.innerText;
            const linkEl = article.querySelector('time')?.closest('a');
            const tweetUrl = linkEl ? linkEl.href : null;
            processTweet(article, text, tweetUrl, getTweetIdFromArticle(article), getTweetTimeFromArticle(article));
        }});
        saveState(Date.now());
    }}

    function catchUpScan() {{
        const state = getState();
        const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
        const items = [];
        articles.forEach(article => {{
            const textEl = article.querySelector('[data-testid="tweetText"]');
            if (!textEl) return;
            const text = textEl.innerText;
            const linkEl = article.querySelector('time')?.closest('a');
            const tweetUrl = linkEl ? linkEl.href : null;
            items.push({{ article, text, tweetUrl, tweetId: getTweetIdFromArticle(article), tweetTime: getTweetTimeFromArticle(article) }});
        }});
        items.sort((a, b) => (b.tweetTime || '').localeCompare(a.tweetTime || ''));
        for (const item of items) {{
            if (state.lastTweetId && item.tweetId === state.lastTweetId) break;
            if (state.lastTweetTime && item.tweetTime && item.tweetTime <= state.lastTweetTime) break;
            processTweet(item.article, item.text, item.tweetUrl, item.tweetId, item.tweetTime);
        }}
        saveState(Date.now());
    }}

    function maybeCatchUpThenScan() {{
        const state = getState();
        const gap = (Date.now() - state.lastRunTime) / (60 * 1000);
        if (gap >= CATCH_UP_THRESHOLD_MINUTES) catchUpScan();
        else scan();
    }}

    let scanTimer = null;
    const observer = new MutationObserver(() => {{
        if (scanTimer) clearTimeout(scanTimer);
        scanTimer = setTimeout(() => {{
            scanTimer = null;
            const state = getState();
            const gapMin = (Date.now() - state.lastRunTime) / (60 * 1000);
            if (gapMin >= CATCH_UP_THRESHOLD_MINUTES) catchUpScan();
            else scan();
        }}, 400);
    }});
    function attachObserver() {{
        const target = document.body;
        if (!target || !(target instanceof Node)) return false;
        observer.observe(target, {{ childList: true, subtree: true }});
        maybeCatchUpThenScan();
        setTimeout(() => {{
            scrollUntilLastSeen().then(() => {{
                catchUpScan();
                setTimeout(() => {{ window.location.reload(); }}, REFRESH_MINUTES * 60 * 1000);
            }});
        }}, INITIAL_WAIT_BEFORE_SCROLL_MS);
        return true;
    }}
    if (!attachObserver()) {{
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', () => attachObserver());
        }} else {{
            const check = () => {{ if (!attachObserver()) setTimeout(check, 50); }};
            setTimeout(check, 0);
        }}
    }}
    setInterval(() => {{ console.log("Alive - " + new Date().toLocaleTimeString() + " - Scraping all tweets..."); }}, 30000);
}})();
"#,
        name_escaped,
        version,
        match_x,
        match_twitter,
        list_id,
        monitor.refresh_minutes
    )
}

#[tauri::command]
fn generate_scrape_all_script(monitor: Monitor) -> Result<String, String> {
    Ok(generate_tampermonkey_script_scrape_all(&monitor))
}

#[tauri::command]
fn parse_list_url(list_url: String) -> Result<Option<String>, String> {
    Ok(parse_list_id_from_url(&list_url))
}

/// Open a URL in the system default browser.
#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    opener::open(url).map_err(|e| e.to_string())
}

/// Derive a safe table name from a monitor name (e.g. "MLB News" -> "mlb_news_tweets").
fn table_name_from_monitor_name(name: &str) -> String {
    let s = name.trim().to_lowercase();
    let slug: String = s
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else if c == ' ' || c == '-' { '_' } else { '\0' })
        .collect();
    let slug: String = slug
        .split('_')
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join("_");
    let base = if slug.is_empty() { "monitor" } else { slug.as_str() };
    format!("{}_tweets", base)
}

/// Return the table name that would be created from this monitor name (e.g. "MLB News" -> "mlb_news_tweets").
#[tauri::command]
fn derive_tweets_table_name(monitor_name: String) -> Result<String, String> {
    Ok(table_name_from_monitor_name(&monitor_name))
}

/// Create a tweets table in news_sources. Table name is derived from monitor_name (e.g. "MLB News" -> "mlb_news_tweets").
/// Requires the tweets API to be running (POST /api/create-table).
#[tauri::command]
fn create_tweets_table(monitor_name: String) -> Result<String, String> {
    let table_name = table_name_from_monitor_name(&monitor_name);
    let base = std::env::var("ODDSMANAGER_TWEETS_API").unwrap_or_else(|_| DEFAULT_TWEETS_API.to_string());
    let url = format!("{}/api/create-table", base.trim_end_matches('/'));
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| e.to_string())?;
    let res = client
        .post(&url)
        .json(&serde_json::json!({ "table_name": table_name }))
        .send()
        .map_err(|e| e.to_string())?;
    let status = res.status();
    let body: serde_json::Value = res.json().map_err(|e| e.to_string())?;
    if status.as_u16() >= 400 {
        let err = body
            .get("error")
            .and_then(|v| v.as_str())
            .unwrap_or("Unknown error");
        return Err(err.to_string());
    }
    body.get("table_name")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .ok_or_else(|| "No table_name in response".to_string())
}

/// Default base URL for the tweets API (run python news/tweets_api.py).
const DEFAULT_TWEETS_API: &str = "http://localhost:8765";

#[derive(serde::Deserialize)]
struct TablesResponse {
    ok: Option<bool>,
    tables: Option<Vec<String>>,
    error: Option<String>,
}

#[derive(serde::Deserialize)]
struct TweetsResponse {
    ok: Option<bool>,
    tweets: Option<Vec<TweetRow>>,
    error: Option<String>,
}

#[derive(serde::Deserialize, serde::Serialize)]
pub struct TweetRow {
    pub id: Option<u64>,
    pub tweet_id: Option<String>,
    pub author_handle: Option<String>,
    pub text: Option<String>,
    pub url: Option<String>,
    pub posted_at: Option<String>,
    pub inserted_at: Option<String>,
}

/// Fetch recent tweets from the local tweets API (mlb_tweets – keyword matches).
#[tauri::command]
fn fetch_recent_tweets(limit: Option<u32>) -> Result<Vec<TweetRow>, String> {
    fetch_tweets_from_path("/api/tweets", limit)
}

/// Fetch recent tweets from mlb_tweets_all (scrape-all, for search).
#[tauri::command]
fn fetch_recent_tweets_all(limit: Option<u32>) -> Result<Vec<TweetRow>, String> {
    fetch_tweets_from_path("/api/tweets/all", limit)
}

/// Fetch recent tweets from golf_tweets (for Golf feed).
#[tauri::command]
fn fetch_recent_tweets_golf(limit: Option<u32>) -> Result<Vec<TweetRow>, String> {
    fetch_tweets_from_path("/api/tweets/golf", limit)
}

/// List table names in news_sources (for Send tweets to dropdown). Requires tweets API running.
#[tauri::command]
fn list_tweets_tables() -> Result<Vec<String>, String> {
    let base = std::env::var("ODDSMANAGER_TWEETS_API").unwrap_or_else(|_| DEFAULT_TWEETS_API.to_string());
    let url = format!("{}/api/tables", base.trim_end_matches('/'));
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| e.to_string())?;
    let res = client.get(&url).send().map_err(|e| e.to_string())?;
    let status = res.status();
    let body: TablesResponse = res.json().map_err(|e| e.to_string())?;
    if status.as_u16() >= 400 {
        return Err(body.error.unwrap_or_else(|| "API error".to_string()));
    }
    body.tables.ok_or_else(|| body.error.unwrap_or_else(|| "No tables key".to_string()))
}

fn fetch_tweets_from_path(path: &str, limit: Option<u32>) -> Result<Vec<TweetRow>, String> {
    let base = std::env::var("ODDSMANAGER_TWEETS_API").unwrap_or_else(|_| DEFAULT_TWEETS_API.to_string());
    let limit = limit.unwrap_or(100).min(500);
    let url = format!("{}{}?limit={}", base.trim_end_matches('/'), path, limit);
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| e.to_string())?;
    let res = client.get(&url).send().map_err(|e| e.to_string())?;
    let status = res.status();
    let body: TweetsResponse = res.json().map_err(|e| e.to_string())?;
    if status.as_u16() >= 400 {
        return Err(body.error.unwrap_or_else(|| status.to_string()));
    }
    body.tweets.ok_or_else(|| body.error.unwrap_or_else(|| "No tweets key".to_string()))
}

/// Port the tweets API binds to (must match tweets_api.py).
const TWEETS_API_PORT: u16 = 8765;

/// Kill any process listening on the given port so we can start a fresh server.
fn kill_processes_on_port(port: u16) {
    #[cfg(windows)]
    {
        let script = format!(
            "Get-NetTCPConnection -LocalPort {} -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}",
            port
        );
        let _ = Command::new("powershell")
            .args(["-NoProfile", "-Command", &script])
            .output();
    }
    #[cfg(not(windows))]
    {
        // Linux: fuser -k 8765/tcp. macOS: lsof -ti:8765 | xargs kill -9
        let _ = Command::new("sh")
            .args(["-c", &format!("fuser -k {}/tcp 2>/dev/null || true", port)])
            .output();
    }
}

/// Start the local tweets API server (python news/tweets_api.py) in the background.
/// Kills any existing process on the port first, then starts a new one.
#[tauri::command]
fn start_tweets_server(_app: tauri::AppHandle, state: State<ServerProcess>) -> Result<(), String> {
    // Stop our own tracked child if any, so we don't leave it running.
    {
        let mut guard = state.0.lock().map_err(|e| e.to_string())?;
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
        }
    }

    // Kill any other process listening on the tweets API port (e.g. leftover from another terminal).
    kill_processes_on_port(TWEETS_API_PORT);
    thread::sleep(Duration::from_secs(1));

    // If something is still on the port (e.g. slow to exit), don't start a second server.
    let addr = SocketAddr::from(([127, 0, 0, 1], TWEETS_API_PORT));
    if TcpStream::connect_timeout(&addr, Duration::from_millis(500)).is_ok() {
        return Err(format!(
            "Port {} is still in use after cleanup. Try closing other terminals or restart the app.",
            TWEETS_API_PORT
        ));
    }

    let root = project_root()?;
    let script = root.join("news").join("tweets_api.py");
    if !script.exists() {
        return Err(format!("tweets_api.py not found at {}", script.display()));
    }
    let python = which_python();
    let stderr_log = root.join("news").join("tweets_api_stderr.log");
    let stderr_file = fs::File::create(&stderr_log).map_err(|e| e.to_string())?;
    let mut cmd = Command::new(&python);
    cmd.arg(&script)
        .current_dir(&root)
        .stderr(Stdio::from(stderr_file));
    let mut child = cmd.spawn().map_err(|e| e.to_string())?;

    // If the process exits quickly, it likely failed (import error, missing deps, etc.).
    thread::sleep(Duration::from_millis(1500));
    if let Ok(Some(status)) = child.try_wait() {
        if !status.success() {
            let err = fs::read_to_string(&stderr_log).unwrap_or_else(|_| "(could not read stderr)".to_string());
            return Err(format!("Tweets API exited: {}", err.trim_end()));
        }
    }

    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    *guard = Some(child);
    Ok(())
}

/// Stop the tweets API server that was started by the app (if any).
#[tauri::command]
fn stop_tweets_server(state: State<ServerProcess>) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    if let Some(mut child) = guard.take() {
        use std::io::ErrorKind;
        match child.kill() {
            Ok(_) => {}
            Err(e) if e.kind() == ErrorKind::InvalidInput || e.kind() == ErrorKind::NotFound => {
                // Already exited; ignore.
            }
            Err(e) => return Err(e.to_string()),
        }
    }
    Ok(())
}

/// Request tweets server status. Returns immediately; result is sent via event "tweets-server-status" (payload: bool).
/// This never blocks the main thread (on Windows, connecting to a refused port can hang for many seconds).
#[tauri::command]
fn tweets_server_status(app: tauri::AppHandle) -> Result<(), String> {
    let base = std::env::var("ODDSMANAGER_TWEETS_API").unwrap_or_else(|_| DEFAULT_TWEETS_API.to_string());
    let url = format!("{}/health", base.trim_end_matches('/'));
    thread::spawn(move || {
        let running = reqwest::blocking::Client::builder()
            .connect_timeout(Duration::from_millis(500))
            .timeout(Duration::from_secs(1))
            .build()
            .and_then(|c| c.get(&url).send())
            .map_or(false, |r| r.status().is_success());
        let _ = app.emit("tweets-server-status", running);
    });
    Ok(())
}

/// Blocking tweets server status check. Returns true if server responds. Use when event API is unavailable.
/// May block up to ~1s on Windows if nothing is listening on the port.
#[tauri::command]
fn tweets_server_status_blocking() -> Result<bool, String> {
    let base = std::env::var("ODDSMANAGER_TWEETS_API").unwrap_or_else(|_| DEFAULT_TWEETS_API.to_string());
    let url = format!("{}/health", base.trim_end_matches('/'));
    let client = reqwest::blocking::Client::builder()
        .connect_timeout(Duration::from_millis(500))
        .timeout(Duration::from_secs(1))
        .build()
        .map_err(|e| e.to_string())?;
    let running = client
        .get(&url)
        .send()
        .map_or(false, |r| r.status().is_success());
    Ok(running)
}

// ---- Kalshi API (local Python server on port 8766) ----

const DEFAULT_KALSHI_API: &str = "http://localhost:8766";
const KALSHI_API_PORT: u16 = 8766;

fn kalshi_base_url() -> String {
    std::env::var("ODDSMANAGER_KALSHI_API").unwrap_or_else(|_| DEFAULT_KALSHI_API.to_string())
}

fn kalshi_get(env: &str, path: &str, params: &[(&str, Option<String>)]) -> Result<serde_json::Value, String> {
    let base = kalshi_base_url().trim_end_matches('/').to_string();
    let url = format!("{}{}", base, path);
    let mut query: Vec<(&str, String)> = vec![("env", env.to_lowercase())];
    for (k, v) in params {
        if let Some(ref val) = v {
            query.push((*k, val.clone()));
        }
    }
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;
    let res = client.get(&url).query(&query).send().map_err(|e| e.to_string())?;
    let status = res.status();
    let body: serde_json::Value = res.json().map_err(|e| e.to_string())?;
    if status.as_u16() >= 400 {
        let err = body.get("error").and_then(|v| v.as_str()).unwrap_or("API error");
        return Err(err.to_string());
    }
    Ok(body)
}

fn kalshi_post_json(env: &str, path: &str, body: serde_json::Value) -> Result<serde_json::Value, String> {
    let base = kalshi_base_url().trim_end_matches('/').to_string();
    let url = format!("{}{}?env={}", base, path, env.to_lowercase());
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;
    let res = client
        .post(&url)
        .json(&body)
        .send()
        .map_err(|e| e.to_string())?;
    let status = res.status();
    let resp_body: serde_json::Value = res.json().map_err(|e| e.to_string())?;
    if status.as_u16() >= 400 {
        let err = resp_body.get("error").and_then(|v| v.as_str()).unwrap_or("API error");
        return Err(err.to_string());
    }
    Ok(resp_body)
}

fn kalshi_delete(env: &str, path: &str) -> Result<serde_json::Value, String> {
    let base = kalshi_base_url().trim_end_matches('/').to_string();
    let url = format!("{}{}?env={}", base, path, env.to_lowercase());
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;
    let res = client.delete(&url).send().map_err(|e| e.to_string())?;
    let status = res.status();
    let body: serde_json::Value = res.json().map_err(|e| e.to_string())?;
    if status.as_u16() >= 400 {
        let err = body.get("error").and_then(|v| v.as_str()).unwrap_or("API error");
        return Err(err.to_string());
    }
    Ok(body)
}

#[tauri::command]
fn kalshi_server_status() -> Result<bool, String> {
    let url = format!("{}/health", kalshi_base_url().trim_end_matches('/'));
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let client = match reqwest::blocking::Client::builder()
            .connect_timeout(Duration::from_millis(400))
            .timeout(Duration::from_secs(1))
            .build()
        {
            Ok(c) => c,
            Err(e) => {
                let _ = tx.send(Err(e.to_string()));
                return;
            }
        };
        let ok = client.get(&url).send().map_or(false, |r| r.status().is_success());
        let _ = tx.send(Ok(ok));
    });
    match rx.recv_timeout(Duration::from_secs(2)) {
        Ok(Ok(running)) => Ok(running),
        Ok(Err(e)) => Err(e),
        Err(_) => Ok(false),
    }
}

#[tauri::command]
fn start_kalshi_server(_app: tauri::AppHandle, state: State<KalshiServerProcess>) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    if let Some(mut child) = guard.take() {
        let _ = child.kill();
    }
    drop(guard);

    kill_processes_on_port(KALSHI_API_PORT);
    thread::sleep(Duration::from_secs(2));

    let addr = SocketAddr::from(([127, 0, 0, 1], KALSHI_API_PORT));
    if TcpStream::connect_timeout(&addr, Duration::from_millis(500)).is_ok() {
        return Err(format!(
            "Port {} is still in use. Try closing other terminals or restart the app.",
            KALSHI_API_PORT
        ));
    }

    let root = project_root()?;
    let script = root.join("betting_outs").join("kalshi").join("kalshi_api.py");
    if !script.exists() {
        return Err(format!("kalshi_api.py not found at {}", script.display()));
    }
    let python = which_python();
    let stderr_log = root.join("betting_outs").join("kalshi").join("kalshi_api_stderr.log");
    if let Some(parent) = stderr_log.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let stderr_file = fs::File::create(&stderr_log).map_err(|e| e.to_string())?;
    let mut cmd = Command::new(&python);
    cmd.arg(&script)
        .current_dir(&root)
        .stderr(Stdio::from(stderr_file));
    let mut child = cmd.spawn().map_err(|e| e.to_string())?;

    thread::sleep(Duration::from_millis(1500));
    if let Ok(Some(status)) = child.try_wait() {
        if !status.success() {
            let err = fs::read_to_string(&stderr_log).unwrap_or_else(|_| "(could not read stderr)".to_string());
            return Err(format!("Kalshi API exited: {}", err.trim_end()));
        }
    }

    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    *guard = Some(child);
    Ok(())
}

#[tauri::command]
fn stop_kalshi_server(state: State<KalshiServerProcess>) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    if let Some(mut child) = guard.take() {
        use std::io::ErrorKind;
        match child.kill() {
            Ok(_) => {}
            Err(e) if e.kind() == ErrorKind::InvalidInput || e.kind() == ErrorKind::NotFound => {}
            Err(e) => return Err(e.to_string()),
        }
    }
    Ok(())
}

#[tauri::command]
fn kalshi_balance(env: Option<String>) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    kalshi_get(env, "/balance", &[])
}

#[tauri::command]
fn kalshi_exchange_status(env: Option<String>) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    kalshi_get(env, "/exchange-status", &[])
}

#[tauri::command]
fn kalshi_orders(
    env: Option<String>,
    limit: Option<u32>,
    cursor: Option<String>,
    status: Option<String>,
) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    let params = [
        ("limit", limit.map(|n| n.to_string())),
        ("cursor", cursor),
        ("status", status),
    ];
    kalshi_get(env, "/orders", &params)
}

#[tauri::command]
fn kalshi_positions(env: Option<String>, limit: Option<u32>, cursor: Option<String>) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    let params = [
        ("limit", limit.map(|n| n.to_string())),
        ("cursor", cursor),
    ];
    kalshi_get(env, "/positions", &params)
}

#[tauri::command]
fn kalshi_markets(p: KalshiMarketsParams) -> Result<serde_json::Value, String> {
    let env = p.env.as_deref().unwrap_or("demo");
    let params = [
        ("limit", p.limit.map(|n| n.to_string())),
        ("cursor", p.cursor.clone()),
        ("status", p.status.clone()),
        ("event_ticker", p.event_ticker.clone()),
        ("series_ticker", p.series_ticker.clone()),
        ("tickers", p.tickers.clone()),
    ];
    kalshi_get(env, "/markets", &params)
}

#[tauri::command]
fn kalshi_market_reciprocal(env: Option<String>, ticker: String) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    kalshi_get(env, "/market-reciprocal", &[("ticker", Some(ticker))])
}

#[tauri::command]
fn kalshi_place_order(
    env: Option<String>,
    ticker: String,
    action: Option<String>,
    side: Option<String>,
    count: u32,
    yes_price: Option<u32>,
    no_price: Option<u32>,
    client_order_id: Option<String>,
    time_in_force: Option<String>,
    expiration_ts: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    let mut body = serde_json::json!({
        "ticker": ticker,
        "action": action.unwrap_or_else(|| "buy".to_string()),
        "side": side.unwrap_or_else(|| "yes".to_string()),
        "count": count,
        "yes_price": yes_price,
        "no_price": no_price,
        "client_order_id": client_order_id,
    });
    if let Some(t) = time_in_force {
        body["time_in_force"] = serde_json::Value::String(t);
    }
    if let Some(ts) = expiration_ts {
        body["expiration_ts"] = ts;
    }
    kalshi_post_json(env, "/order", body)
}

#[tauri::command]
fn kalshi_cancel_order(env: Option<String>, order_id: String) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    kalshi_delete(env, &format!("/order/{}", order_id))
}

#[tauri::command]
fn kalshi_batch_place_orders(
    env: Option<String>,
    orders: Vec<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    let body = serde_json::json!({ "orders": orders });
    kalshi_post_json(env, "/orders/batch", body)
}

#[tauri::command]
fn kalshi_market_making_strategies(env: Option<String>) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    kalshi_get(env, "/market-making/strategies", &[])
}

#[tauri::command]
fn kalshi_market_making_restart(
    env: Option<String>,
    strategy_id: String,
) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    kalshi_post_json(
        env,
        &format!("/market-making/strategy/{}/restart", strategy_id),
        serde_json::json!({}),
    )
}

#[tauri::command]
fn kalshi_market_making_create(
    env: Option<String>,
    markets: Vec<String>,
    order_size: u32,
    refill_mode: String,
    stop_max_shares: Option<u64>,
    stop_max_dollars: Option<u64>,
    check_interval_sec: u32,
) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    let body = serde_json::json!({
        "markets": markets,
        "order_size": order_size,
        "refill_mode": refill_mode,
        "stop_max_shares": stop_max_shares,
        "stop_max_dollars": stop_max_dollars,
        "check_interval_sec": check_interval_sec,
    });
    kalshi_post_json(env, "/market-making/strategies", body)
}

#[tauri::command]
fn kalshi_orderbook(env: Option<String>, ticker: String) -> Result<serde_json::Value, String> {
    let env = env.as_deref().unwrap_or("demo");
    let path = format!("/markets/{}/orderbook", ticker);
    kalshi_get(env, &path, &[])
}

fn market_maker_script_content(tickers: &[String]) -> String {
    let ticker_list = if tickers.is_empty() {
        r#""TICKER1", "TICKER2"  # Add your market tickers"#.to_string()
    } else {
        tickers
            .iter()
            .map(|t| format!(r#""{}""#, t.replace('\\', "\\\\").replace('"', r#"\"#)))
            .collect::<Vec<_>>()
            .join(", ")
    };
    format!(
        r#"#!/usr/bin/env python3
"""
Barebones Kalshi market maker.
Generated by OddsManager. Adapt for your strategy and run on VPS.
"""
import os
import time

# Set these or use .env: KALSHI_API_KEY, KALSHI_PRIVATE_KEY_PATH
os.chdir(os.path.dirname(os.path.abspath(__file__)))

TICKERS = [{}]
ORDER_SIZE = 1
CHECK_INTERVAL_SEC = 30
REFILL_MODE = "same"  # "same" or "median"

def main():
    # TODO: Import kalshi client from betting_outs/kalshi
    # TODO: Poll orderbook, place orders, refill on fill
    print("Market maker stub. Implement order placement and refill logic.")
    while True:
        for t in TICKERS:
            print(f"  Check {{t}}...")
        time.sleep(CHECK_INTERVAL_SEC)

if __name__ == "__main__":
    main()
"#,
        ticker_list,
    )
}

/// Generate a barebones market maker script. Returns the script content as a string.
#[tauri::command]
fn generate_market_maker_script(tickers: Vec<String>) -> Result<String, String> {
    Ok(market_maker_script_content(&tickers))
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
struct MmStakeConfig {
    ticker: String,
    #[serde(default)]
    title: Option<String>,
    shares: u32,
    side: String,
    yes_price: Option<u32>,
    no_price: Option<u32>,
    pct_reload: Option<u32>,
    repost_base: Option<String>,
    cents_off: Option<i32>,
    max_shares: Option<u64>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
struct MmStrategyConfig {
    event_ticker: String,
    #[serde(default)]
    env: Option<String>,
    check_interval_sec: u32,
    alert_webhook_url: Option<String>,
    stakes: Vec<MmStakeConfig>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
struct CombinedNoConfig {
    event_ticker: String,
    #[serde(default)]
    env: Option<String>,
    check_interval_sec: u32,
    max_combined: u32,
    shares: u32,
    tickers: Vec<String>,
    alert_webhook_url: Option<String>,
}

/// Sanitize event ticker for use in systemd service name (lowercase alphanumeric only).
fn mm_service_suffix(event_ticker: &str) -> String {
    event_ticker
        .to_lowercase()
        .chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .collect::<String>()
}

fn mm_service_installer_content(config: &MmStrategyConfig) -> String {
    let script_name = format!(
        "mm_{}.py",
        config.event_ticker.replace(['-', ' '], "_")
    );
    let service_suffix = mm_service_suffix(&config.event_ticker);
    let service_name = format!("oddsmanager-mm-{}", service_suffix);
    let env_str = config
        .env
        .as_deref()
        .map(|e| format!(r#"Environment="KALSHI_ENV={}""#, e.to_uppercase()))
        .unwrap_or_else(|| r#"Environment="KALSHI_ENV=prod""#.to_string());
    format!(
        r#"#!/bin/bash
# Install and start the market-making strategy as a systemd service.
# Run this on your VPS (e.g. DigitalOcean) from market_making_services/.
#
# Prerequisites:
#   - Project cloned to PROJECT_ROOT
#   - venv created and deps installed
#   - .env with KALSHI_API_KEY, KALSHI_PRIVATE_KEY_PATH
#   - Strategy script in market_making/, this installer in market_making_services/
#
# Usage (from market_making_services/): ./install_{install_sh}.sh

set -e

_SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Find project root: walk up until we find a dir containing market_making/
find_project_root() {{
  local d="$1"
  while [[ -n "$d" && "$d" != "/" ]]; do
    [[ -d "$d/market_making" ]] && echo "$d" && return
    d="$(dirname "$d")"
  done
  echo ""
}}
PROJECT_ROOT="${{PROJECT_ROOT:-$(find_project_root "$_SCRIPT_DIR")}}"
if [[ -z "$PROJECT_ROOT" ]]; then
  echo "Error: Could not find project root (no parent dir contains market_making/). Set PROJECT_ROOT explicitly."
  exit 1
fi
DEPLOY_USER="${{DEPLOY_USER:-root}}"
SCRIPT_NAME="{script_name}"
SERVICE_NAME="{service_name}"

# Default: /home/root/venvs/myenv1/bin/python. Override: PYTHON=$PROJECT_ROOT/venv/bin/python
PYTHON="${{PYTHON:-/home/root/venvs/myenv1/bin/python}}"
SCRIPT_PATH="${{PROJECT_ROOT}}/market_making/{script_name}"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "Error: Strategy script not found at $SCRIPT_PATH"
  echo "Copy $SCRIPT_NAME to market_making/ first."
  exit 1
fi

SVC_FILE="/etc/systemd/system/${{SERVICE_NAME}}.service"
echo "Creating $SVC_FILE ..."
sudo tee "$SVC_FILE" > /dev/null << EOF
[Unit]
Description=OddsManager MM - {event_ticker}
After=network.target oddsmanager-kalshi-api.service

[Service]
Type=simple
User=$DEPLOY_USER
Group=$DEPLOY_USER
WorkingDirectory=$PROJECT_ROOT
EnvironmentFile=$PROJECT_ROOT/.env
Environment=PATH=$(dirname $PYTHON):/usr/local/bin:/usr/bin:/bin
{env_line}
ExecStart=$PYTHON $SCRIPT_PATH
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd, enabling and starting $SERVICE_NAME ..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager
echo ""
echo "Done. Use: sudo systemctl status $SERVICE_NAME  # check status"
echo "        sudo journalctl -u $SERVICE_NAME -f     # follow logs"
"#,
        install_sh = config.event_ticker.replace(['-', ' '], "_"),
        script_name = script_name,
        service_name = service_name,
        event_ticker = config.event_ticker,
        env_line = env_str,
    )
}

fn mm_strategy_script_content(config: &MmStrategyConfig) -> String {
    let config_json = serde_json::to_string(config).unwrap_or_else(|_| "{}".to_string());
    let config_escaped = config_json.replace("'''", "\\'''");
    format!(
        r#"#!/usr/bin/env python3
"""
Kalshi per-stake market maker. Generated by OddsManager.
Run from project root: python mm_Event_26.py
Or save as market_making/config.json and run: python -m market_making.bot
"""
import json
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_root = _here
while _root and not os.path.isdir(os.path.join(_root, "market_making")):
    _parent = os.path.dirname(_root)
    if _parent == _root:
        break
    _root = _parent
if not _root:
    _root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)
os.chdir(_root)

from market_making.bot import run

CONFIG_JSON = r'''{}'''

if __name__ == "__main__":
    config = json.loads(CONFIG_JSON)
    run(config)
"#,
        config_escaped,
    )
}

#[tauri::command]
fn generate_mm_strategy_script(config: MmStrategyConfig) -> Result<String, String> {
    Ok(mm_strategy_script_content(&config))
}

#[tauri::command]
fn save_mm_config(app: tauri::AppHandle, config: MmStrategyConfig) -> Result<String, String> {
    let json = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
    let default_name = format!("mm_{}_config.json", config.event_ticker.replace(['-', ' '], "_"));
    let mut dialog = app
        .dialog()
        .file()
        .add_filter("JSON", &["json"])
        .set_file_name(&default_name);
    if let Ok(root) = project_root() {
        dialog = dialog.set_directory(root);
    }
    let path = dialog.blocking_save_file();
    match path {
        Some(p) => {
            let path_buf = p.into_path().map_err(|e| e.to_string())?;
            fs::write(&path_buf, &json).map_err(|e| e.to_string())?;
            Ok(path_buf.display().to_string())
        }
        None => Err("Save cancelled".to_string()),
    }
}

#[tauri::command]
fn save_mm_strategy_script(app: tauri::AppHandle, config: MmStrategyConfig) -> Result<String, String> {
    let script = mm_strategy_script_content(&config);
    let default_name = format!("mm_{}.py", config.event_ticker.replace(['-', ' '], "_"));
    let mut dialog = app
        .dialog()
        .file()
        .add_filter("Python", &["py"])
        .set_file_name(&default_name);
    if let Ok(root) = project_root() {
        let market_making = root.join("market_making");
        let dir = if market_making.exists() { market_making } else { root };
        dialog = dialog.set_directory(dir);
    }
    let path = dialog.blocking_save_file();
    match path {
        Some(p) => {
            let path_buf = p.into_path().map_err(|e| e.to_string())?;
            fs::write(&path_buf, &script).map_err(|e| e.to_string())?;

            // Also write the VPS installer bash script to src-tauri/market_making_services/
            if let Ok(root) = project_root() {
                let services_dir = root.join("desktop").join("src-tauri").join("market_making_services");
                if fs::create_dir_all(&services_dir).is_ok() {
                    let install_name = format!(
                        "install_mm_{}.sh",
                        config.event_ticker.replace(['-', ' '], "_")
                    );
                    let install_path = services_dir.join(&install_name);
                    let install_content = mm_service_installer_content(&config);
                    if let Err(e) = fs::write(&install_path, &install_content) {
                        eprintln!("Could not write installer to {:?}: {}", install_path, e);
                    }
                }
            }

            Ok(path_buf.display().to_string())
        }
        None => Err("Save cancelled".to_string()),
    }
}

fn combined_no_strategy_script_content(config: &CombinedNoConfig) -> String {
    let config_json = serde_json::to_string(config).unwrap_or_else(|_| "{}".to_string());
    let config_escaped = config_json.replace("'''", "\\'''");
    format!(
        r#"#!/usr/bin/env python3
"""
Combined No Spread bot. Generated by OddsManager.
Offers No liquidity when combined best No ask < max_combined.
Run from project root: python combined_no_Event.py
"""
import json
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_root = _here
while _root and not os.path.isdir(os.path.join(_root, "market_making")):
    _parent = os.path.dirname(_root)
    if _parent == _root:
        break
    _root = _parent
if not _root:
    _root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)
os.chdir(_root)

from market_making.combined_no_bot import run

CONFIG_JSON = r'''{}'''

if __name__ == "__main__":
    config = json.loads(CONFIG_JSON)
    run(config)
"#,
        config_escaped,
    )
}

fn combined_no_service_installer_content(config: &CombinedNoConfig) -> String {
    let script_name = format!(
        "combined_no_{}.py",
        config.event_ticker.replace(['-', ' '], "_")
    );
    let service_suffix = mm_service_suffix(&config.event_ticker);
    let service_name = format!("oddsmanager-combinedno-{}", service_suffix);
    let env_str = config
        .env
        .as_deref()
        .map(|e| format!(r#"Environment="KALSHI_ENV={}""#, e.to_uppercase()))
        .unwrap_or_else(|| r#"Environment="KALSHI_ENV=prod""#.to_string());
    format!(
        r#"#!/bin/bash
# Install and start the Combined No Spread bot as a systemd service.
# Run this on your VPS from market_making_services/.

set -e

_SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
find_project_root() {{
  local d="$1"
  while [[ -n "$d" && "$d" != "/" ]]; do
    [[ -d "$d/market_making" ]] && echo "$d" && return
    d="$(dirname "$d")"
  done
  echo ""
}}
PROJECT_ROOT="${{PROJECT_ROOT:-$(find_project_root "$_SCRIPT_DIR")}}"
if [[ -z "$PROJECT_ROOT" ]]; then
  echo "Error: Could not find project root. Set PROJECT_ROOT explicitly."
  exit 1
fi
DEPLOY_USER="${{DEPLOY_USER:-root}}"
SCRIPT_NAME="{script_name}"
SERVICE_NAME="{service_name}"

PYTHON="${{PYTHON:-/home/root/venvs/myenv1/bin/python}}"
SCRIPT_PATH="${{PROJECT_ROOT}}/market_making/{script_name}"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "Error: Strategy script not found at $SCRIPT_PATH"
  exit 1
fi

SVC_FILE="/etc/systemd/system/${{SERVICE_NAME}}.service"
echo "Creating $SVC_FILE ..."
sudo tee "$SVC_FILE" > /dev/null << EOF
[Unit]
Description=OddsManager Combined No - {event_ticker}
After=network.target oddsmanager-kalshi-api.service

[Service]
Type=simple
User=$DEPLOY_USER
Group=$DEPLOY_USER
WorkingDirectory=$PROJECT_ROOT
EnvironmentFile=$PROJECT_ROOT/.env
Environment=PATH=$(dirname $PYTHON):/usr/local/bin:/usr/bin:/bin
{env_line}
ExecStart=$PYTHON $SCRIPT_PATH
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd, enabling and starting $SERVICE_NAME ..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager
echo ""
echo "Done. Use: sudo systemctl status $SERVICE_NAME"
"#,
        script_name = script_name,
        service_name = service_name,
        event_ticker = config.event_ticker,
        env_line = env_str,
    )
}

#[tauri::command]
fn generate_combined_no_strategy_script(config: CombinedNoConfig) -> Result<String, String> {
    Ok(combined_no_strategy_script_content(&config))
}

#[tauri::command]
fn save_combined_no_strategy_script(app: tauri::AppHandle, config: CombinedNoConfig) -> Result<String, String> {
    let script = combined_no_strategy_script_content(&config);
    let default_name = format!(
        "combined_no_{}.py",
        config.event_ticker.replace(['-', ' '], "_")
    );
    let mut dialog = app
        .dialog()
        .file()
        .add_filter("Python", &["py"])
        .set_file_name(&default_name);
    if let Ok(root) = project_root() {
        let market_making = root.join("market_making");
        let dir = if market_making.exists() { market_making } else { root };
        dialog = dialog.set_directory(dir);
    }
    let path = dialog.blocking_save_file();
    match path {
        Some(p) => {
            let path_buf = p.into_path().map_err(|e| e.to_string())?;
            fs::write(&path_buf, &script).map_err(|e| e.to_string())?;

            if let Ok(root) = project_root() {
                let services_dir = root.join("desktop").join("src-tauri").join("market_making_services");
                if fs::create_dir_all(&services_dir).is_ok() {
                    let install_name = format!(
                        "install_combined_no_{}.sh",
                        config.event_ticker.replace(['-', ' '], "_")
                    );
                    let install_path = services_dir.join(&install_name);
                    let install_content = combined_no_service_installer_content(&config);
                    if let Err(e) = fs::write(&install_path, &install_content) {
                        eprintln!("Could not write installer to {:?}: {}", install_path, e);
                    }
                }
            }

            Ok(path_buf.display().to_string())
        }
        None => Err("Save cancelled".to_string()),
    }
}

/// Generate market maker script and save via native save dialog.
#[tauri::command]
fn save_market_maker_script(app: tauri::AppHandle, tickers: Vec<String>) -> Result<String, String> {
    let script = market_maker_script_content(&tickers);
    let path = app
        .dialog()
        .file()
        .add_filter("Python", &["py"])
        .set_file_name("market_maker.py")
        .blocking_save_file();
    match path {
        Some(p) => {
            let path_buf = p.into_path().map_err(|e| e.to_string())?;
            fs::write(&path_buf, &script).map_err(|e| e.to_string())?;
            Ok(path_buf.display().to_string())
        }
        None => Err("Save cancelled".to_string()),
    }
}

/// Resolve OddsManager project root (parent of desktop/, where news/ and scripts live).
fn project_root() -> Result<PathBuf, String> {
    // 1) Explicit env (e.g. set by user or launcher)
    if let Ok(root) = std::env::var("ODDSMANAGER_PROJECT_ROOT") {
        let p = PathBuf::from(&root);
        let news = p.join("news");
        if news.join("run_list_monitor.py").exists() || news.join("tweets_api.py").exists() {
            return Ok(p);
        }
    }
    // 2) Current working directory (e.g. "cargo tauri dev" from repo root or from desktop/)
    if let Ok(cwd) = std::env::current_dir() {
        let news = cwd.join("news");
        if news.join("run_list_monitor.py").exists() || news.join("tweets_api.py").exists() {
            return Ok(cwd);
        }
        if let Some(parent) = cwd.parent() {
            let news = parent.join("news");
            if news.join("run_list_monitor.py").exists() || news.join("tweets_api.py").exists() {
                return Ok(parent.to_path_buf());
            }
        }
    }
    // 3) Exe-relative: exe is .../desktop/target/debug/odds-manager-desktop.exe -> go up to desktop/ then to project root
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let mut dir = exe.parent().ok_or("no exe dir")?.to_path_buf();
    for _ in 0..2 {
        dir = dir.parent().ok_or("no parent")?.to_path_buf();
    }
    let root = dir.parent().ok_or("no project root")?.to_path_buf();
    let news = root.join("news");
    if news.join("run_list_monitor.py").exists() || news.join("tweets_api.py").exists() {
        Ok(root)
    } else {
        Err(
            "Project root not found (expected news/run_list_monitor.py or news/tweets_api.py). Set ODDSMANAGER_PROJECT_ROOT to your OddsManager folder, or run the app from that folder.".to_string(),
        )
    }
}

/// Start list monitor (run_list_monitor.py) for this monitor config. Writes config to app data and spawns
/// python news/run_list_monitor.py --config <path>. Process runs in background, scraping every 60s.
#[tauri::command]
fn start_headless_monitor(app: tauri::AppHandle, monitor: Monitor) -> Result<(), String> {
    let root = project_root()?;
    let script = root.join("news").join("run_list_monitor.py");
    if !script.exists() {
        return Err(format!("Script not found: {}", script.display()));
    }
    let config_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&config_dir).map_err(|e| e.to_string())?;
    let config_path = config_dir.join(format!("monitor_{}.json", monitor.id));
    let config = monitor_config_json(&monitor);
    fs::write(&config_path, serde_json::to_string_pretty(&config).unwrap()).map_err(|e| e.to_string())?;
    let python = which_python();
    let mut cmd = Command::new(python);
    cmd.arg(script)
        .arg("--config")
        .arg(&config_path)
        .current_dir(&root);
    cmd.spawn().map_err(|e| e.to_string())?;
    Ok(())
}

fn which_python() -> String {
    std::env::var("ODDSMANAGER_PYTHON").unwrap_or_else(|_| "python".to_string())
}

/// Bring the main app window to front and focus it (e.g. when showing an alert).
#[tauri::command]
fn bring_main_window_to_front(app: tauri::AppHandle) -> Result<(), String> {
    let window = app.get_webview_window("main").ok_or("Main window not found")?;
    window.show().map_err(|e| e.to_string())?;
    window.set_focus().map_err(|e| e.to_string())?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_notification::init())
        .manage(ServerProcess(Mutex::new(None)))
        .manage(KalshiServerProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            list_monitors,
            add_monitor,
            delete_monitor,
            generate_script,
            generate_scrape_all_script,
            parse_list_url,
            open_url,
            derive_tweets_table_name,
            create_tweets_table,
            list_tweets_tables,
            bring_main_window_to_front,
            start_headless_monitor,
            fetch_recent_tweets,
            fetch_recent_tweets_all,
            fetch_recent_tweets_golf,
            start_tweets_server,
            stop_tweets_server,
            tweets_server_status,
            tweets_server_status_blocking,
            kalshi_server_status,
            start_kalshi_server,
            stop_kalshi_server,
            kalshi_balance,
            kalshi_exchange_status,
            kalshi_orders,
            kalshi_positions,
            kalshi_markets,
            kalshi_market_reciprocal,
            kalshi_place_order,
            kalshi_cancel_order,
            kalshi_batch_place_orders,
            kalshi_market_making_strategies,
            kalshi_market_making_restart,
            kalshi_market_making_create,
            kalshi_orderbook,
            generate_market_maker_script,
            generate_combined_no_strategy_script,
            save_combined_no_strategy_script,
            save_market_maker_script,
            generate_mm_strategy_script,
            save_mm_strategy_script,
            save_mm_config,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
