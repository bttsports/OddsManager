# Create a Windows scheduled task that starts the X list monitor at user logon.
# Run from repo root: powershell -ExecutionPolicy Bypass -File news/install_list_monitor_task.ps1
# Or from news/: powershell -ExecutionPolicy Bypass -File install_list_monitor_task.ps1

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$batPath = Join-Path $scriptDir "start_list_monitor.bat"

if (-not (Test-Path $batPath)) {
    Write-Error "Not found: $batPath"
    exit 1
}

$taskName = "OddsManager X List Monitor"
$action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
    Write-Host "Task '$taskName' created. It will run at logon and start the list monitor."
    Write-Host "To remove: Unregister-ScheduledTask -TaskName '$taskName'"
} catch {
    Write-Error $_
    exit 1
}
