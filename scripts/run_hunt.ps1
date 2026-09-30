param(
    [switch]$Demo,
    [switch]$DryRun,
    [switch]$PublishDemo
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"

New-Item -ItemType Directory -Force $LogDir | Out-Null

$Date = Get-Date -Format "yyyy-MM-dd"
$LogFile = Join-Path $LogDir "hunt-$Date.log"

$LogRetentionDays = 30

try {
    $ExpiredLogs = Get-ChildItem -Path $LogDir -Filter "hunt-*.log" `
        -File `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.FullName -ne $LogFile -and
            $_.LastWriteTime -lt (Get-Date).AddDays(-$LogRetentionDays)
        }

    foreach ($ExpiredLog in $ExpiredLogs) {
        Remove-Item $ExpiredLog.FullName -Force
    }
}
catch {
    Write-Host (
        "Log cleanup skipped: {0}" -f $_.Exception.Message
    )
}

$PythonArgs = @(
    ".\run.py",
    "--keywords-file",
    ".\data\keywords.json"
)

if ($Demo) {
    $PythonArgs += "--demo"
}

if ($DryRun) {
    $PythonArgs += "--dry-run"
}

if ($PublishDemo) {
    $PythonArgs += "--publish-demo"
}

$StartedAt = Get-Date

"==================================================" |
    Tee-Object -FilePath $LogFile -Append

("Hunt started: {0}" -f $StartedAt.ToString("yyyy-MM-dd HH:mm:ss")) |
    Tee-Object -FilePath $LogFile -Append

& $Python @PythonArgs 2>&1 |
    Tee-Object -FilePath $LogFile -Append

$ExitCode = $LASTEXITCODE
$FinishedAt = Get-Date

("Hunt finished: {0}" -f $FinishedAt.ToString("yyyy-MM-dd HH:mm:ss")) |
    Tee-Object -FilePath $LogFile -Append

("Exit code: {0}" -f $ExitCode) |
    Tee-Object -FilePath $LogFile -Append

"==================================================" |
    Tee-Object -FilePath $LogFile -Append

exit $ExitCode
