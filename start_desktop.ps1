<# 
Launcher for the OddsManager desktop app (dev).

- Sets ODDSMANAGER_PROJECT_ROOT so the Rust backend can find the repo
- Runs `cargo tauri dev` from desktop/src-tauri

Usage:
  Right‑click this file and choose “Run with PowerShell”
  or run from a PowerShell prompt:
    powershell -ExecutionPolicy Bypass -File .\start_desktop.ps1
#>

$ErrorActionPreference = "Stop"

# Point the app at your OddsManager project root
$env:ODDSMANAGER_PROJECT_ROOT = "C:\Users\davpo\VSCodeProjects\OddsManager"

# Change into the Tauri project and run the dev app
Set-Location -Path (Join-Path $env:ODDSMANAGER_PROJECT_ROOT "desktop\src-tauri")
cargo tauri dev

