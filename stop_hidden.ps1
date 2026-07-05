$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimePath = Join-Path $Root "data\runtime.json"

if (-not (Test-Path -LiteralPath $RuntimePath)) {
    exit 0
}

$runtime = Get-Content -LiteralPath $RuntimePath -Raw | ConvertFrom-Json
$pidValue = [int]$runtime.pid
if (-not $pidValue) {
    Remove-Item -LiteralPath $RuntimePath -Force
    exit 0
}

$processInfo = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
if ($processInfo -and ($processInfo.ProcessName -eq "python" -or $processInfo.ProcessName -eq "pythonw")) {
    Stop-Process -Id $pidValue -Force
}

Remove-Item -LiteralPath $RuntimePath -Force
