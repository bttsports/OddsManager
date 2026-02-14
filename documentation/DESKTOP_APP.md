# OddsManager Desktop App (Rust + Tauri)

This document describes how to run, build, and work with the OddsManager desktop application.

## Prerequisites

- **Rust** (1.70 or newer). Install from [rustup.rs](https://rustup.rs).
- **Tauri CLI** (for `tauri dev` and `tauri build`). Install once with:
  ```bash
  cargo install tauri-cli --version "^2.0.0" --locked
  ```
- **Windows**: WebView2 is usually already present on Windows 10/11. If not, the Tauri docs recommend installing it.

## Project location

The desktop app lives under:

- `desktop/` – root of the Tauri app
- `desktop/ui/` – frontend (HTML, CSS, JS)
- `desktop/src-tauri/` – Rust backend and Tauri config

## Commands (run from repo root)

### Start the app in development

To open the app window and load the UI from `desktop/ui/`:

```bash
cd desktop
cargo tauri dev
```

- **What it does**: Compiles the Rust backend, opens the app window, and serves the UI from `desktop/ui/`.
- **First run**: May take a few minutes while dependencies compile.

### Build a release executable

To produce an optimized build and installer:

```bash
cd desktop
cargo tauri build
```

- **What it does**: Builds the Rust app in release mode and creates the installer/bundle.
- **Output**: Under `desktop/src-tauri/target/release/` you get the `.exe` (Windows) or the appropriate binary for your OS. The installer is in `target/release/bundle/`.

### Run the built app without Tauri CLI

After a successful build you can run the binary directly:

```bash
cd desktop/src-tauri
cargo run --release
```

Or run the executable from `desktop/src-tauri/target/release/` (e.g. `odds-manager-desktop.exe` on Windows).

### Run only the Rust backend (no window)

To compile and run the Rust part (e.g. for quick tests), from `desktop/src-tauri`:

```bash
cargo run
```

This still starts the full Tauri app (including the window). To work on Rust-only logic, run or test the library: `cargo test` in `desktop/src-tauri`.

### Run tests

```bash
cd desktop/src-tauri
cargo test
```

### Check code without building

```bash
cd desktop/src-tauri
cargo check
```

## Summary table

| Goal                         | Command (from repo root)     |
|-----------------------------|------------------------------|
| Start app in dev            | `cd desktop && cargo tauri dev` |
| Build release + installer   | `cd desktop && cargo tauri build` |
| Run release binary          | `cd desktop/src-tauri && cargo run --release` |
| Run tests                   | `cd desktop/src-tauri && cargo test` |
| Check Rust compiles         | `cd desktop/src-tauri && cargo check` |

## Where data is stored

- Monitors (list URL + keywords) are saved in the **app data directory** as `monitors.json`.
  - Windows: `%APPDATA%\com.oddsmanager.desktop\`
  - macOS: `~/Library/Application Support/com.oddsmanager.desktop/`
  - Linux: `~/.local/share/com.oddsmanager.desktop/` (or similar per XDG).

## Using a monitor

1. **Create a monitor** in the app: name, X list URL (e.g. `https://x.com/i/lists/52021139`), and keywords (one per line or comma-separated).
2. **Generate script**: Click “Generate script” for that monitor. The app copies a Tampermonkey script to the clipboard.
3. **Install in Tampermonkey**: Create a new script in Tampermonkey, paste the clipboard content, save.
4. **Open the list**: Click “Open list in browser” so the list page loads on x.com. The Tampermonkey script will run there and watch for your keywords.

The generated script is tailored to that monitor’s list ID and keywords and uses the same logic as `news/x_list_monitor.js`.

## Headless monitor (background, no browser tab)

When you **add a monitor** or click **Start headless monitor**, the app starts a background process that runs the same logic in a headless Chromium browser and writes matching tweets to `news_sources.mlb_tweets`.

**Requirements:** Python on PATH (or `ODDSMANAGER_PYTHON`); `pip install playwright` then `playwright install chromium`; project root is auto-detected from `desktop/` or set `ODDSMANAGER_PROJECT_ROOT`; ensure `news_sources.mlb_tweets` exists (run `python create_news_sources_db.py` once).

## Tweets API (script → DB and Notifications tab)

The Tampermonkey script sends matching tweets to a local API that writes to `news_sources.mlb_tweets`. The app’s **Notifications** tab reads from the same API.

Run the API from repo root: `python news/tweets_api.py`. It listens on **http://localhost:8765**. Endpoints: **POST /api/tweet** (body: tweet_id, author_handle, text, url?, posted_at?), **GET /api/tweets?limit=100**. Install with `pip install flask flask-cors`. Override URL via `ODDSMANAGER_TWEETS_API`.
