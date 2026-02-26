"""
Long-running X list monitor: one browser, one page, run the scraper every 60 seconds.
Uses a persistent browser context so X stays logged in. Injects the same logic as
x_list_monitor.js (whole-word keywords, cache, state, catch-up) and reports matches
via __onMatch -> DB (no dependency on tweets_api.py for the monitor).

Run from project root: python news/run_list_monitor.py --config news/monitor_config.json
Optional: --headed (show browser), --interval 60 (seconds between scans).

For "run always": use the Windows scheduled task (see news/README_LIST_MONITOR.md).
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import sync_playwright

import db
from os_check import USER, PASSWORD, HOST


def parse_tweet_id_from_url(url):
    if not url:
        return None
    parts = url.rstrip("/").split("/")
    if "status" in parts:
        idx = parts.index("status")
        if idx + 1 < len(parts):
            return parts[idx + 1].split("?")[0]
    return None


def get_inject_js(keywords, list_id, catch_up_minutes, max_cache_size):
    """Same logic as x_list_monitor.js but calls window.__onMatch instead of GM_xmlhttpRequest."""
    keywords_json = json.dumps(keywords)
    list_id_safe = json.dumps(str(list_id))
    return f"""
    (function() {{
        const KEYWORDS = {keywords_json};
        const LIST_ID = {list_id_safe};
        const CATCH_UP_THRESHOLD_MINUTES = {catch_up_minutes};
        const MAX_CACHE_SIZE = {max_cache_size};
        const STORAGE_KEY = "X_MONITOR_SEEN_CACHE_" + LIST_ID;
        const STATE_KEY = "X_MONITOR_STATE_" + LIST_ID;

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
            const m = linkEl.href.match(/\\/status\\/(\\d+)/);
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

        function escapeRegex(s) {{
            return s.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
        }}

        function hasWholeWordMatch(text, keywords) {{
            for (const kw of keywords) {{
                const re = new RegExp('\\\\b' + escapeRegex(kw) + '\\\\b', 'i');
                if (re.test(text)) return true;
            }}
            return false;
        }}

        function processMatch(article, text, tweetUrl, tweetId, tweetTime) {{
            const cache = getSeenCache();
            const fingerprint = text.substring(0, 120);
            if (cache.includes(fingerprint)) return;
            if (!hasWholeWordMatch(text, KEYWORDS)) return;
            const author = getAuthorFromArticle(article);
            const id = tweetId || getTweetIdFromArticle(article);
            const time = tweetTime || getTweetTimeFromArticle(article);
            if (window.__onMatch) window.__onMatch({{ tweetId: id || String(Date.now()), authorHandle: author, text, url: tweetUrl, postedAt: time }});
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
                const tweetId = getTweetIdFromArticle(article);
                const tweetTime = getTweetTimeFromArticle(article);
                processMatch(article, text, tweetUrl, tweetId, tweetTime);
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
                const tweetId = getTweetIdFromArticle(article);
                const tweetTime = getTweetTimeFromArticle(article);
                items.push({{ article, text, tweetUrl, tweetId, tweetTime }});
            }});
            const byTime = (a, b) => (b.tweetTime || '').localeCompare(a.tweetTime || '');
            items.sort(byTime);
            for (const item of items) {{
                if (state.lastTweetId && item.tweetId === state.lastTweetId) break;
                if (state.lastTweetTime && item.tweetTime && item.tweetTime <= state.lastTweetTime) break;
                processMatch(item.article, item.text, item.tweetUrl, item.tweetId, item.tweetTime);
            }}
            saveState(Date.now());
        }}

        function maybeCatchUpThenScan() {{
            const state = getState();
            const now = Date.now();
            const gap = (now - state.lastRunTime) / (60 * 1000);
            if (gap >= CATCH_UP_THRESHOLD_MINUTES) catchUpScan();
            else scan();
        }}

        window.__scanList = scan;
        window.__maybeCatchUpThenScan = maybeCatchUpThenScan;
        maybeCatchUpThenScan();
    }})();
    """


def main():
    parser = argparse.ArgumentParser(description="X list monitor: one process, scrape every N seconds")
    parser.add_argument("--config", default=str(REPO_ROOT / "news" / "monitor_config.json"), help="Path to JSON config")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between scans (default 60)")
    parser.add_argument("--headed", action="store_true", help="Show browser window (default: headless)")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"Config not found: {config_path}", file=sys.stderr)
        print("Create news/monitor_config.json with list_url, keywords, and optional list_id.", file=sys.stderr)
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    list_url = config.get("list_url")
    keywords = [k.strip().lower() for k in config.get("keywords", []) if k.strip()]
    list_id = config.get("list_id", "default")
    catch_up_minutes = max(1, int(config.get("catch_up_threshold_minutes", 5)))
    max_cache_size = max(50, int(config.get("max_cache_size", 200)))

    if not list_url or not keywords:
        print("Config must include list_url and keywords.", file=sys.stderr)
        sys.exit(1)

    try:
        database = db.DBS["news_sources"]
    except KeyError:
        import mysql.connector
        database = mysql.connector.connect(
            user=USER, password=PASSWORD, host=HOST, database="news_sources"
        )

    seen_tweet_ids = set()

    def on_match(payload):
        try:
            text = payload.get("text") or ""
            url = payload.get("url") or ""
            author_handle = (payload.get("authorHandle") or "unknown").lstrip("@")
            posted_at = payload.get("postedAt")
            tweet_id = parse_tweet_id_from_url(url) or payload.get("tweetId")
            if not tweet_id:
                tweet_id = str(hash(text[:200]))
            if tweet_id in seen_tweet_ids:
                return
            seen_tweet_ids.add(tweet_id)
            db.insert_mlb_tweet(
                database,
                tweet_id=tweet_id,
                author_handle=author_handle,
                text=text,
                url=url or None,
                posted_at=posted_at,
            )
            print(f"[DB] {author_handle}: {text[:60]}...")
        except Exception as e:
            print(f"[on_match error] {e}", file=sys.stderr)

    user_data_dir = REPO_ROOT / ".playwright_x_profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    inject_js = get_inject_js(keywords, list_id, catch_up_minutes, max_cache_size)
    interval_ms = args.interval * 1000

    print(f"List monitor: {list_url} (keywords: {len(keywords)}, interval: {args.interval}s, profile: {user_data_dir})")
    print("One-time login: run with --headed, log in on X, then close; next runs can be headless.")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=not args.headed,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.expose_function("__onMatch", on_match)

        page.goto(list_url, wait_until="networkidle", timeout=60000)
        # Use evaluate() instead of add_script_tag() so X's CSP doesn't block inline script
        page.evaluate(inject_js)

        try:
            while True:
                page.wait_for_timeout(interval_ms)
                page.evaluate("window.__maybeCatchUpThenScan && window.__maybeCatchUpThenScan()")
        except KeyboardInterrupt:
            print("Stopping list monitor.")
        finally:
            context.close()


if __name__ == "__main__":
    main()
