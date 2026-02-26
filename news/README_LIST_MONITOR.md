# X List Monitor (automated flow)

One long-running process: browser stays open on the list page, and the same scraper logic runs **every 60 seconds** (no full page reload). Matches are written to `news_sources.mlb_tweets`.

## Quick start

1. **Config**  
   Edit `news/monitor_config.json`: set `list_url` and `keywords`. Optionally `list_id` (for localStorage keys), `catch_up_threshold_minutes`, `max_cache_size`.

2. **One-time login**  
   From repo root:
   ```bash
   python news/run_list_monitor.py --config news/monitor_config.json --headed
   ```
   Log in on X in the opened browser, then stop the script (Ctrl+C). The session is stored in `.playwright_x_profile/`. After that you can run headless.

3. **Run manually**  
   ```bash
   python news/run_list_monitor.py --config news/monitor_config.json
   ```
   Or double‑click `news/start_list_monitor.bat` (from repo root or from `news/`).

4. **Run always (Windows)**  
   Install a scheduled task that starts the monitor at logon:
   ```powershell
   cd C:\Users\davpo\VSCodeProjects\OddsManager
   powershell -ExecutionPolicy Bypass -File news/install_list_monitor_task.ps1
   ```
   The task **OddsManager X List Monitor** will run at every logon and keep the monitor process running (scraper runs every 60 seconds).  
   To remove the task:  
   `Unregister-ScheduledTask -TaskName "OddsManager X List Monitor"`

## Options

- `--interval 60` — seconds between scans (default 60).
- `--headed` — show browser window (default is headless).
- `--config path` — config file (default `news/monitor_config.json`).

## Dependencies

- **Python**: `pip install playwright` then `playwright install chromium` (one-time). The package is in `requirements.txt`.
- **Database**: `news_sources` and `mlb_tweets` (same as the rest of the app). The monitor writes directly to the DB; it does **not** require `tweets_api.py` to be running.
- **Tweets API** (optional): if you want the desktop app to show recent tweets, run `python news/tweets_api.py` (http://localhost:8765) separately.

## Notes

- The scraper logic matches `news/x_list_monitor.js` (whole-word keywords, cache, catch-up when the script hasn’t run for a while).
- Profile directory: `.playwright_x_profile/` (gitignored). Delete it to force a fresh login.
