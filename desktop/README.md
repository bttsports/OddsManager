# OddsManager Desktop

Rust + Tauri desktop app for managing X (Twitter) list monitors. Create monitors (list URL + keywords), generate TamperMonkey scripts, and open list URLs in the browser.

## Quick start

From the **repo root**:

```bash
cd desktop
cargo tauri dev
```

(Install Tauri CLI once: `cargo install tauri-cli --version "^2.0.0" --locked`)

## Docs

- **[documentation/DESKTOP_APP.md](../documentation/DESKTOP_APP.md)** – full run/build/test instructions and where data is stored.
- **[documentation/COMMANDS_QUICK_REFERENCE.md](../documentation/COMMANDS_QUICK_REFERENCE.md)** – “do this command to do x” quick reference.

## Layout

- `ui/` – frontend (HTML, CSS, JS); no npm build.
- `src-tauri/` – Rust backend, Tauri config, and capabilities.

## Flow

1. Add a monitor: name, X list URL (e.g. `https://x.com/i/lists/52021139`), keywords (one per line or comma-separated).
2. Click **Generate script** → script is copied to the clipboard.
3. In Tampermonkey: New script → paste → save.
4. Click **Open list in browser** and use the list page on x.com; the script will run there and alert on keyword matches.

The generated script mirrors the logic in `news/x_list_monitor.js` but uses the list ID and keywords you configured.
