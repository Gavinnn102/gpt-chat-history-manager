param(
    [string]$OutDir = (Join-Path (Split-Path -Parent $PSScriptRoot) "dist"),
    [string]$PackageName = "gpt-chat-history-manager"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$OutDir = [IO.Path]::GetFullPath($OutDir)
$StageRoot = Join-Path $OutDir "$PackageName-staging"
$ZipPath = Join-Path $OutDir "$PackageName.zip"

$SensitiveTerms = @()
foreach ($term in @($env:USERPROFILE, $env:CHAT_HISTORY_HOME)) {
    if ($term -and $term.Trim()) {
        $SensitiveTerms += $term.Trim()
    }
}
if ($env:CHAT_HISTORY_RELEASE_SENSITIVE_TERMS) {
    $SensitiveTerms += $env:CHAT_HISTORY_RELEASE_SENSITIVE_TERMS -split ";" |
        Where-Object { $_ -and $_.Trim() } |
        ForEach-Object { $_.Trim() }
}

function Get-RelativePath {
    param([string]$Path)
    $rootPath = $RepoRoot
    if (-not $rootPath.EndsWith([IO.Path]::DirectorySeparatorChar)) {
        $rootPath += [IO.Path]::DirectorySeparatorChar
    }
    $rootUri = New-Object System.Uri($rootPath)
    $pathUri = New-Object System.Uri((Resolve-Path -LiteralPath $Path).Path)
    return [Uri]::UnescapeDataString($rootUri.MakeRelativeUri($pathUri).ToString())
}

function Test-IsExcluded {
    param([IO.FileInfo]$File)

    $relative = Get-RelativePath $File.FullName
    $parts = $relative -split "/"
    $blockedDirs = @(".git", "data", "inbox", "backups", "exports", "reports", "logs", "dist", "__pycache__", ".pytest_cache", ".venv", "venv")
    foreach ($part in $parts) {
        if ($blockedDirs -contains $part) {
            return $true
        }
    }

    if ($File.Extension -in @(".pyc", ".lnk", ".log", ".tmp")) {
        return $true
    }
    if ($File.Name -like "pending_import_*.json" -or $File.Name -like "classified_import_*.json") {
        return $true
    }
    if ($File.Name -like "ai_work_packet_*.json" -or $File.Name -like "ai_work_packet_*.md") {
        return $true
    }
    if ($File.Name -like "GPT聊天记录资料库*.html") {
        return $true
    }
    if ($File.Name -like "*线程补充*") {
        return $true
    }
    return $false
}

function Get-PublicFiles {
    Get-ChildItem -LiteralPath $RepoRoot -Recurse -File -Force |
        Where-Object { -not (Test-IsExcluded $_) } |
        Sort-Object FullName
}

function Assert-NoSensitiveTerms {
    param([array]$Files)

    foreach ($file in $Files) {
        try {
            $text = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8
        } catch {
            continue
        }
        foreach ($term in $SensitiveTerms) {
            if ($text.Contains($term)) {
                $relative = Get-RelativePath $file.FullName
                throw "Sensitive term found in $relative"
            }
        }
    }
}

$publicFiles = @(Get-PublicFiles)
Assert-NoSensitiveTerms $publicFiles

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
if (Test-Path -LiteralPath $StageRoot) {
    Remove-Item -LiteralPath $StageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $StageRoot -Force | Out-Null

$manifestFiles = @()
foreach ($file in $publicFiles) {
    $relative = Get-RelativePath $file.FullName
    $target = Join-Path $StageRoot ($relative -replace "/", [IO.Path]::DirectorySeparatorChar)
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName
    $manifestFiles += [ordered]@{
        path = $relative
        bytes = $file.Length
        sha256 = $hash.Hash
    }
}

$manifest = [ordered]@{
    name = $PackageName
    generated_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    file_count = $manifestFiles.Count
    files = $manifestFiles
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $StageRoot "RELEASE_MANIFEST.json") -Encoding UTF8

$stagedFiles = @(Get-ChildItem -LiteralPath $StageRoot -Recurse -File -Force)
Assert-NoSensitiveTerms $stagedFiles

if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $StageRoot "*") -DestinationPath $ZipPath -Force

Write-Host "Release zip: $ZipPath"
Write-Host "Files: $($manifestFiles.Count)"
