"""
Headless X list monitor: runs the same logic as the Tampermonkey script
in a Playwright browser, and feeds matching tweets into news_sources.mlb_tweets.

Run from project root: python news/headless_list_monitor.py --config <path_to_config.json>
Config JSON: { "list_url": "...", "keywords": ["a","b"], "refresh_minutes": 1 }

Requires: pip install playwright && playwright install chromium
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Run from repo root so these imports work
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import sync_playwright

# Import after path is set
import db
from os_check import USER, PASSWORD, HOST


def parse_tweet_id_from_url(url):
    """Extract Twitter tweet ID from status URL e.g. .../status/1234567890"""
    if not url:
        return None
    parts = url.rstrip("/").split("/")
    if "status" in parts:
        idx = parts.index("status")
        if idx + 1 < len(parts):
            return parts[idx + 1].split("?")[0]
    return None


def main():
    parser = argparse.ArgumentParser(description="Headless X list monitor -> DB")
    parser.add_argument("--config", required=True, help="Path to JSON config file")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)
    list_url = config["list_url"]
    keywords = [k.strip().lower() for k in config.get("keywords", []) if k.strip()]
    refresh_minutes = max(1, int(config.get("refresh_minutes", 1)))

    if not keywords:
        print("No keywords in config; exiting.")
        return

    try:
        database = db.DBS["news_sources"]
    except KeyError:
        import mysql.connector
        database = mysql.connector.connect(
            user=USER, password=PASSWORD, host=HOST, database="news_sources"
        )

    seen_tweet_ids = set()

    def on_match(payload):
        """Called from injected JS when a tweet matches keywords."""
        try:
            text = payload.get("text") or ""
            url = payload.get("url") or ""
            author_handle = (payload.get("authorHandle") or "unknown").lstrip("@")
            posted_at = payload.get("postedAt")  # ISO string or None
            tweet_id = parse_tweet_id_from_url(url) or payload.get("tweetId")
            if not tweet_id:
                tweet_id = str(hash(text[:200]))  # fallback dedupe
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

    # Injected script: same scan logic as Tampermonkey, but calls __onMatch instead of notification
    keywords_json = json.dumps(keywords)
    inject_js = f"""
    (function() {{
        const KEYWORDS = {keywords_json};
        const seen = new Set();

        function scan() {{
            const articles = document.querySelectorAll('article[data-testid="tweet"]');
            articles.forEach(article => {{
                const textEl = article.querySelector('[data-testid="tweetText"]');
                if (!textEl) return;
                const text = textEl.innerText;
                const fingerprint = text.substring(0, 120);
                if (seen.has(fingerprint)) return;
                const linkEl = article.querySelector('time')?.closest('a');
                const tweetUrl = linkEl ? linkEl.href : null;
                let authorHandle = 'unknown';
                const authorLink = article.querySelector('a[href^="/"]');
                if (authorLink && authorLink.href) {{
                    const m = authorLink.href.match(/^https?:\\/\\/[^/]+\\/([^/]+)/);
                    if (m) authorHandle = m[1];
                }}
                let postedAt = null;
                const timeEl = article.querySelector('time');
                if (timeEl && timeEl.getAttribute('datetime')) postedAt = timeEl.getAttribute('datetime');
                const lowerText = text.toLowerCase();
                for (const kw of KEYWORDS) {{
                    if (lowerText.includes(kw)) {{
                        seen.add(fingerprint);
                        if (window.__onMatch) window.__onMatch({{ text, url: tweetUrl, authorHandle, postedAt }});
                        break;
                    }}
                }}
            }});
        }}

        window.__scanList = scan;
        scan();
    }})();
    """

    print(f"Headless monitor: {list_url} (keywords: {len(keywords)}, refresh: {refresh_minutes}m)")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        page.expose_function("__onMatch", on_match)

        page.goto(list_url, wait_until="networkidle", timeout=60000)
        page.add_script_tag(content=inject_js)

        try:
            while True:
                page.evaluate("window.__scanList && window.__scanList()")
                page.wait_for_timeout(refresh_minutes * 60 * 1000)
                page.reload(wait_until="networkidle", timeout=60000)
                page.add_script_tag(content=inject_js)
        except KeyboardInterrupt:
            print("Stopping monitor.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
