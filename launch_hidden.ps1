$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $Root "app\launcher.py"

$python = $null
$pythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
if ($pythonCmd) {
    $candidate = Join-Path (Split-Path -Parent $pythonCmd.Source) "pythonw.exe"
    if (Test-Path -LiteralPath $candidate) {
        $python = $candidate
    } else {
        $python = $pythonCmd.Source
    }
}

if (-not $python) {
    $pywCmd = Get-Command pyw.exe -ErrorAction SilentlyContinue
    if ($pywCmd) {
        $python = $pywCmd.Source
    }
}

if (-not $python) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("没有找到 Python。", "GPT聊天记录资料库") | Out-Null
    exit 1
}

Start-Process -FilePath $python -ArgumentList "`"$Launcher`"" -WorkingDirectory $Root -WindowStyle Hidden
