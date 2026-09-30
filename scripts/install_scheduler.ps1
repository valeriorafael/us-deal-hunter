$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Launcher = Join-Path $ProjectRoot "scripts\run_hunt.ps1"

if (-not (Test-Path $Launcher)) {
    throw "Launcher not found: $Launcher"
}

$TaskName = "US Deal Hunter - Production"

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Launcher`""

$Triggers = @(
    (New-ScheduledTaskTrigger -Daily -At "02:00"),
    (New-ScheduledTaskTrigger -Daily -At "08:00"),
    (New-ScheduledTaskTrigger -Daily -At "14:00"),
    (New-ScheduledTaskTrigger -Daily -At "20:00")
)

$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $Triggers `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Runs the US Deal Hunter four times per day."

Register-ScheduledTask `
    -TaskName $TaskName `
    -InputObject $Task `
    -Force | Out-Null

Disable-ScheduledTask `
    -TaskName $TaskName | Out-Null

Write-Host ""
Write-Host "Task created: $TaskName"
Write-Host "Status: DISABLED"
Write-Host "Schedule: 02:00, 08:00, 14:00, 20:00"
