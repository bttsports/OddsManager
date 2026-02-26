// ==UserScript==
// @name         X List Monitor: MLB – Scrape All Tweets
// @namespace    http://tampermonkey.net/
// @version      2026.02.19
// @description  Same list as MLB monitor; scrapes all tweets (no keyword filter). For later player/team matching.
// @match        https://x.com/i/lists/2022369077642015042
// @match        https://twitter.com/i/lists/2022369077642015042
// @grant        GM_xmlhttpRequest
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-end
// ==/UserScript==

(function() {
    'use strict';

    const API_URL = "http://localhost:8765";
    // POST to this URL inserts into news_sources.mlb_tweets_all (same as GET /api/tweets/all).
    const TWEET_POST_URL = "http://localhost:8765/api/tweet/all";
    // Same list as x_list_monitor_mlb.js – no keywords; we scrape everything for later filtering
    const LIST_ID = "2022369077642015042";
    const REFRESH_MINUTES = 1;
    const CATCH_UP_THRESHOLD_MINUTES = 5;
    const STORAGE_KEY = "X_MONITOR_SEEN_CACHE_" + LIST_ID + "_ScrapeAll";
    const STATE_KEY = "X_MONITOR_STATE_" + LIST_ID + "_ScrapeAll";
    const MAX_CACHE_SIZE = 200;
    const SCROLL_STEP_PX = 800;
    const SCROLL_WAIT_MS = 1800;
    const MAX_SCROLL_STEPS = 50;
    const INITIAL_WAIT_BEFORE_SCROLL_MS = 2000;

    function getVisibleTweetIds() {
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        const ids = new Set();
        articles.forEach(function(a) {
            const id = getTweetIdFromArticle(a);
            if (id) ids.add(id);
        });
        return ids;
    }

    function scrollUntilLastSeen() {
        return new Promise(function(resolve) {
            const state = getState();
            const lastId = state.lastTweetId;
            if (!lastId) {
                var count = 0;
                function doScroll() {
                    window.scrollBy(0, SCROLL_STEP_PX);
                    count++;
                    if (count >= 6) resolve();
                    else setTimeout(doScroll, SCROLL_WAIT_MS);
                }
                setTimeout(doScroll, SCROLL_WAIT_MS);
                return;
            }
            var scrollCount = 0;
            var lastScrollHeight = 0;
            function step() {
                var ids = getVisibleTweetIds();
                if (ids.has(lastId) || scrollCount >= MAX_SCROLL_STEPS) {
                    resolve();
                    return;
                }
                var sh = document.documentElement.scrollHeight;
                if (sh === lastScrollHeight && scrollCount > 4) {
                    resolve();
                    return;
                }
                lastScrollHeight = sh;
                window.scrollBy(0, SCROLL_STEP_PX);
                scrollCount++;
                setTimeout(step, SCROLL_WAIT_MS);
            }
            setTimeout(step, SCROLL_WAIT_MS);
        });
    }

    console.log("🚀 MLB List Scrape-All Starting (same list, no keyword filter)...");

    function getSeenCache() {
        const data = localStorage.getItem(STORAGE_KEY);
        return data ? JSON.parse(data) : [];
    }

    function saveToCache(fingerprint) {
        let cache = getSeenCache();
        if (!cache.includes(fingerprint)) {
            cache.push(fingerprint);
            if (cache.length > MAX_CACHE_SIZE) cache = cache.slice(-MAX_CACHE_SIZE);
            localStorage.setItem(STORAGE_KEY, JSON.stringify(cache));
        }
    }

    function getState() {
        const data = localStorage.getItem(STATE_KEY);
        return data ? JSON.parse(data) : { lastRunTime: 0, lastTweetId: null, lastTweetTime: null };
    }

    function saveState(lastRunTime, lastTweetId, lastTweetTime) {
        const s = getState();
        localStorage.setItem(STATE_KEY, JSON.stringify({
            lastRunTime: lastRunTime !== undefined ? lastRunTime : s.lastRunTime,
            lastTweetId: lastTweetId !== undefined ? lastTweetId : s.lastTweetId,
            lastTweetTime: lastTweetTime !== undefined ? lastTweetTime : s.lastTweetTime
        }));
    }

    function getTweetIdFromArticle(article) {
        const linkEl = article.querySelector('time')?.closest('a');
        if (!linkEl || !linkEl.href) return null;
        const m = linkEl.href.match(/\/status\/(\d+)/);
        return m ? m[1] : null;
    }

    function getTweetTimeFromArticle(article) {
        const timeEl = article.querySelector('time');
        return timeEl ? timeEl.getAttribute('datetime') : null;
    }

    function getAuthorFromArticle(article) {
        const authorLink = article.querySelector('a[href^="/"]');
        if (authorLink && authorLink.href) {
            const m = authorLink.href.match(/^https?:\/\/[^/]+\/([^/]+)/);
            if (m) return m[1];
        }
        return "unknown";
    }

    function sendToApi(tweetId, authorHandle, text, url, postedAt) {
        GM_xmlhttpRequest({
            method: "POST",
            url: TWEET_POST_URL,
            headers: { "Content-Type": "application/json" },
            data: JSON.stringify({
                tweet_id: tweetId,
                author_handle: authorHandle,
                text: text,
                url: url || null,
                posted_at: postedAt || null
            }),
            onload: function(res) {
                if (res.status >= 200 && res.status < 300) {
                    console.log("%c📤 Sent (scrape-all): " + authorHandle, "color: #00ba7c;");
                } else {
                    console.warn("API " + res.status);
                }
            },
            onerror: function() {
                console.warn("API failed (run python news/tweets_api.py)");
            }
        });
    }

    // Process every tweet (no keyword check) – dedupe by cache only
    function processTweet(article, text, tweetUrl, tweetId, tweetTime) {
        const cache = getSeenCache();
        const fingerprint = text.substring(0, 120);
        if (cache.includes(fingerprint)) return;
        const author = getAuthorFromArticle(article);
        const id = tweetId || getTweetIdFromArticle(article);
        const time = tweetTime || getTweetTimeFromArticle(article);
        sendToApi(id || String(Date.now()), author, text, tweetUrl, time);
        saveToCache(fingerprint);
        saveState(Date.now(), id, time);
    }

    function scan() {
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        articles.forEach(article => {
            const textEl = article.querySelector('[data-testid="tweetText"]');
            if (!textEl) return;
            const text = textEl.innerText;
            const linkEl = article.querySelector('time')?.closest('a');
            const tweetUrl = linkEl ? linkEl.href : null;
            processTweet(article, text, tweetUrl, getTweetIdFromArticle(article), getTweetTimeFromArticle(article));
        });
        saveState(Date.now());
    }

    function catchUpScan() {
        const state = getState();
        const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
        const items = [];
        articles.forEach(article => {
            const textEl = article.querySelector('[data-testid="tweetText"]');
            if (!textEl) return;
            const text = textEl.innerText;
            const linkEl = article.querySelector('time')?.closest('a');
            const tweetUrl = linkEl ? linkEl.href : null;
            items.push({
                article,
                text,
                tweetUrl,
                tweetId: getTweetIdFromArticle(article),
                tweetTime: getTweetTimeFromArticle(article)
            });
        });
        items.sort((a, b) => (b.tweetTime || '').localeCompare(a.tweetTime || ''));
        for (const item of items) {
            if (state.lastTweetId && item.tweetId === state.lastTweetId) break;
            if (state.lastTweetTime && item.tweetTime && item.tweetTime <= state.lastTweetTime) break;
            processTweet(item.article, item.text, item.tweetUrl, item.tweetId, item.tweetTime);
        }
        saveState(Date.now());
    }

    let scanTimer = null;

    function maybeCatchUpThenScan() {
        const state = getState();
        const gap = (Date.now() - state.lastRunTime) / (60 * 1000);
        if (gap >= CATCH_UP_THRESHOLD_MINUTES) catchUpScan();
        else scan();
    }

    const observer = new MutationObserver(() => {
        if (scanTimer) clearTimeout(scanTimer);
        scanTimer = setTimeout(() => {
            scanTimer = null;
            const state = getState();
            const gapMin = (Date.now() - state.lastRunTime) / (60 * 1000);
            if (gapMin >= CATCH_UP_THRESHOLD_MINUTES) catchUpScan();
            else scan();
        }, 400);
    });

    function attachObserver() {
        const target = document.body;
        if (!target || !(target instanceof Node)) return false;
        observer.observe(target, { childList: true, subtree: true });
        maybeCatchUpThenScan();
        setTimeout(function() {
            scrollUntilLastSeen().then(function() {
                catchUpScan();
                setTimeout(function() {
                    console.log("🔄 Refreshing List...");
                    window.location.reload();
                }, REFRESH_MINUTES * 60 * 1000);
            });
        }, INITIAL_WAIT_BEFORE_SCROLL_MS);
        return true;
    }
    if (!attachObserver()) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => { attachObserver(); });
        } else {
            const check = () => { if (!attachObserver()) setTimeout(check, 50); };
            setTimeout(check, 0);
        }
    }

    setInterval(() => {
        console.log(`Alive - ${new Date().toLocaleTimeString()} - Scraping all tweets (no keywords)...`);
    }, 30000);
})();
