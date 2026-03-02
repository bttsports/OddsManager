<# 
Launcher for the OddsManager desktop app (no hot‑reload).

- Sets ODDSMANAGER_PROJECT_ROOT so the Rust backend can find the repo
- Runs `cargo run --no-default-features` from desktop/src-tauri (no dev watcher)

Usage:
  Right‑click this file and choose “Run with PowerShell”
  or run from a PowerShell prompt:
    powershell -ExecutionPolicy Bypass -File .\start_desktop.ps1
#>

$ErrorActionPreference = "Stop"

# Point the app at your OddsManager project root
$env:ODDSMANAGER_PROJECT_ROOT = "C:\Users\davpo\VSCodeProjects\OddsManager"

# Enable full backtrace on panic (for debugging)
$env:RUST_BACKTRACE = "1"

# Change into the Tauri project and run the app without the dev watcher
Set-Location -Path (Join-Path $env:ODDSMANAGER_PROJECT_ROOT "desktop\src-tauri")
cargo run --no-default-features

