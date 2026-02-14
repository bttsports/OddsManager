// ==UserScript==
// @name         X List Monitor (DB)
// @namespace    http://tampermonkey.net/
// @version      2025.02.14
// @description  X list keyword monitor – sends matching tweets to local API (no desktop notifications)
// @match        https://x.com/*
// @match        https://twitter.com/*
// @grant        GM_xmlhttpRequest
// @run-at       document-end
// ==/UserScript==

// README: Run the tweets API so the script can save tweets: python news/tweets_api.py (http://localhost:8765)
// TESTING: Reset seen cache: localStorage.removeItem("X_MONITOR_SEEN_CACHE_52021139")
//          Reset catch-up state: localStorage.removeItem("X_MONITOR_STATE_52021139")

(function() {
    'use strict';

    const API_URL = "http://localhost:8765";
    const KEYWORDS = ['is in','injured','injury','is out','is in','active','questionable','uncertain','play',
                      'coin', 'inactive', 'will play', 'will start', 'rule out', 'ruled out', 'ruled in',
                     'rule in'];
    const LIST_ID = "52021139";
    const REFRESH_MINUTES = 1;
    const CATCH_UP_THRESHOLD_MINUTES = 5;
    const STORAGE_KEY = "X_MONITOR_SEEN_CACHE_" + LIST_ID;
    const STATE_KEY = "X_MONITOR_STATE_" + LIST_ID;
    const MAX_CACHE_SIZE = 200;

    console.log("🚀 Monitor Starting (DB)...");

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
        localStorage.setItem(STATE_KEY, JSON.stringify({
            lastRunTime: lastRunTime || getState().lastRunTime,
            lastTweetId: lastTweetId !== undefined ? lastTweetId : getState().lastTweetId,
            lastTweetTime: lastTweetTime !== undefined ? lastTweetTime : getState().lastTweetTime
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
            url: API_URL + "/api/tweet",
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
                    console.log("%c📤 Sent to DB: " + authorHandle, "color: #00ba7c;");
                } else {
                    console.warn("API error " + res.status, res.responseText);
                }
            },
            onerror: function() {
                console.warn("API request failed (is python news/tweets_api.py running?)");
            }
        });
    }

    function processMatch(article, text, tweetUrl, tweetId, tweetTime) {
        const cache = getSeenCache();
        const fingerprint = text.substring(0, 120);
        if (cache.includes(fingerprint)) return;
        const lowerText = text.toLowerCase();
        for (const kw of KEYWORDS) {
            if (lowerText.includes(kw.toLowerCase())) {
                const author = getAuthorFromArticle(article);
                const id = tweetId || getTweetIdFromArticle(article);
                const time = tweetTime || getTweetTimeFromArticle(article);
                sendToApi(id || String(Date.now()), author, text, tweetUrl, time);
                saveToCache(fingerprint);
                saveState(Date.now(), id, time);
                break;
            }
        }
    }

    function scan() {
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        articles.forEach(article => {
            const textEl = article.querySelector('[data-testid="tweetText"]');
            if (!textEl) return;
            const text = textEl.innerText;
            const linkEl = article.querySelector('time')?.closest('a');
            const tweetUrl = linkEl ? linkEl.href : null;
            const tweetId = getTweetIdFromArticle(article);
            const tweetTime = getTweetTimeFromArticle(article);
            processMatch(article, text, tweetUrl, tweetId, tweetTime);
        });
        saveState(Date.now());
    }

    function catchUpScan() {
        console.log("🔄 Catch-up: scraping tweets until last seen...");
        const state = getState();
        const articles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
        const items = [];
        articles.forEach(article => {
            const textEl = article.querySelector('[data-testid="tweetText"]');
            if (!textEl) return;
            const text = textEl.innerText;
            const linkEl = article.querySelector('time')?.closest('a');
            const tweetUrl = linkEl ? linkEl.href : null;
            const tweetId = getTweetIdFromArticle(article);
            const tweetTime = getTweetTimeFromArticle(article);
            items.push({ article, text, tweetUrl, tweetId, tweetTime });
        });
        const byTime = (a, b) => {
            const tA = a.tweetTime || '';
            const tB = b.tweetTime || '';
            return tB.localeCompare(tA);
        };
        items.sort(byTime);
        let processed = 0;
        for (const item of items) {
            if (state.lastTweetId && item.tweetId === state.lastTweetId) break;
            if (state.lastTweetTime && item.tweetTime && item.tweetTime <= state.lastTweetTime) break;
            processMatch(item.article, item.text, item.tweetUrl, item.tweetId, item.tweetTime);
            processed++;
        }
        saveState(Date.now());
        if (processed > 0) console.log("Catch-up: processed " + processed + " tweet(s).");
    }

    function maybeCatchUpThenScan() {
        const state = getState();
        const now = Date.now();
        const gap = (now - state.lastRunTime) / (60 * 1000);
        if (gap >= CATCH_UP_THRESHOLD_MINUTES) {
            catchUpScan();
        } else {
            scan();
        }
    }

    const observer = new MutationObserver(() => {
        const state = getState();
        const now = Date.now();
        if ((now - state.lastRunTime) / (60 * 1000) >= CATCH_UP_THRESHOLD_MINUTES) return;
        scan();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    setTimeout(() => {
        console.log("🔄 Refreshing List...");
        window.location.reload();
    }, REFRESH_MINUTES * 60 * 1000);

    setInterval(() => {
        console.log(`Alive - ${new Date().toLocaleTimeString()} - Watching keywords...`);
    }, 30000);

    maybeCatchUpThenScan();
})();
