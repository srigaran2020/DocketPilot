# Register (or remove) the weekly law update in Windows Task Scheduler.
#     .\tools\schedule_law_update.ps1                      # every Sunday at 10:00
#     .\tools\schedule_law_update.ps1 -Day Saturday -At 21:30
#     .\tools\schedule_law_update.ps1 -Remove
# The task runs tools\run_law_update.ps1 as you, only while you are signed in to Windows (no password is stored).
# If the laptop is off at that time, it runs as soon as possible after you next sign in.
param(
    [ValidateSet("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")]
    [string]$Day = "Sunday",
    [string]$At = "10:00",
    [switch]$Remove
)
$name = "DocketPilot weekly law update"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed the task '$name'." -ForegroundColor Yellow
    exit 0
}
$script = Join-Path $PSScriptRoot "run_law_update.ps1"
$root = Split-Path -Parent $PSScriptRoot
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Fetches every Act from India Code and records changed sections in DocketPilot. No AI is used." -Force | Out-Null
$t = Get-ScheduledTask -TaskName $name
Write-Host "Scheduled '$name': every $Day at $At (state: $($t.State))." -ForegroundColor Green
Write-Host "Run it now with:  Start-ScheduledTask -TaskName '$name'   Logs: data\law_updates\"
