<#
make_consult_bundle.ps1
- ChatGPT相談用スナップショット/差分バンドル生成（仕様 v1.6.2 準拠）
- Updated: 2026-05-13 21:45
- DocSet: 202605132145
Description:
  This script generates a consultation bundle for ChatGPT based on a local Git repository.
  It supports four modes: lightweight map, full repository snapshot, partial snapshot (include), and diff.
  The output is organized into parts with size limits, and includes an index, tree, and manifest.

Usage examples:
  # NOTE:
  # - 標準実行系: pwsh（PowerShell 7+）
  # - powershell.exe（Windows PowerShell 5.1）は非対応
  # - RepoRoot はあなたの環境に合わせて変更してください
  # - v1.5.0: 公開配布向けに consult.config.json へ除外ルールを集約します

  # ------------------------------------------------------------
  # Mode D: map（本文なし軽量地図）
  # ------------------------------------------------------------
  pwsh -File tools\chatgpt\make_consult_bundle.ps1 -Mode map -RepoRoot "C:\xampp\htdocs"

  # ------------------------------------------------------------
  # Mode C: repo（全体横断スナップショット）
  # ------------------------------------------------------------
  pwsh -File tools\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs"

  # 設定ファイルを明示する例（未指定時は tools\chatgpt\consult.config.json → .consult\consult.config.json の順に自動探索）
  pwsh -File tools\chatgpt\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs" -ConfigPath ".consult\consult.config.json"

  # 複数行（読みやすさ重視）
  pwsh -File tools\chatgpt\make_consult_bundle.ps1 `
    -Mode repo `
    -RepoRoot "C:\xampp\htdocs"

  # ------------------------------------------------------------
  # Mode A: include（範囲指定スナップショット）
  # ------------------------------------------------------------
  pwsh -File tools\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "common"

  # 複数パス指定（配列）
  pwsh -File tools\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "common","admin","db\schema"

  # v1.4.5: ファイル名のみ/フォルダ名のみ指定（同名複数ヒット時は停止 / ワイルドカード非対応）
  pwsh -File tools\chatgpt\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "Navigation.php","Loader.php"

  # 複数行（読みやすさ重視）
  pwsh -File tools\chatgpt\make_consult_bundle.ps1 `
    -Mode include `
    -RepoRoot "C:\xampp\htdocs" `
    -IncludePaths "common","admin","db\schema"

  # ------------------------------------------------------------
  # Mode B: diff（差分バンドル）
  # ------------------------------------------------------------
  # 未コミット差分（既定: HEAD vs 作業ツリー）
  pwsh -File tools\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs"

  # staged 差分
  pwsh -File tools\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -Staged

  # ref 間差分
  pwsh -File tools\chatgpt\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -DiffBase HEAD~1 -DiffTarget HEAD
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("map", "repo", "include", "diff")]
    [string]$Mode,

    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,

    [string]$CaseName = "",

    [string]$ConfigPath = "",

    [string[]]$IncludePaths = @(),

    [switch]$AllowDocSetFolders,
    [switch]$KeepBundleDir,
    [switch]$Diag,

    [int]$MaxBytesPerPart = 536870912,   # 512MB
    [int]$MaxCharsPerPart = 300000,
    [int]$MaxCharsPerFile = 300000,

    [switch]$Staged,
    [switch]$UnstagedOnly,
    [string]$DiffBase,
    [string]$DiffTarget
)

$null = $AllowDocSetFolders, $KeepBundleDir, $Diag, $CaseName, $ConfigPath, $MaxBytesPerPart, $MaxCharsPerPart, $MaxCharsPerFile, $Staged, $UnstagedOnly, $DiffBase, $DiffTarget
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-RequiredPwsh {
    $currentVersion = $PSVersionTable.PSVersion
    if ($null -eq $currentVersion -or $currentVersion.Major -lt 7) {
        $hostLabel = if ($PSVersionTable.PSEdition) { $PSVersionTable.PSEdition } else { "WindowsPowerShell" }
        $scriptPath = if ($PSCommandPath) { $PSCommandPath } else { "tools\chatgpt\make_consult_bundle.ps1" }
        throw ("Unsupported PowerShell host: {0} {1}. This script requires PowerShell 7+ (pwsh). Re-run with: pwsh -File `"{2}`" -Mode {3} -RepoRoot `"{4}`"" -f $hostLabel, $currentVersion, $scriptPath, $Mode, $RepoRoot)
    }
}

Assert-RequiredPwsh

# ----------------------------
# Time (JST fixed)
# ----------------------------
$JstOffset = [TimeSpan]::FromHours(9)
function Get-JstNow {
    return [DateTimeOffset]::UtcNow.ToOffset($JstOffset)
}

# ----------------------------
# Helpers: path / IO
# ----------------------------
function Resolve-FullPath([string]$path) {
    return [System.IO.Path]::GetFullPath($path)
}

function ConvertTo-RelativePath([string]$baseFull, [string]$targetFull) {
    $baseUri = [Uri]((Resolve-FullPath $baseFull).TrimEnd('\') + '\')
    $targetUri = [Uri](Resolve-FullPath $targetFull)
    $rel = $baseUri.MakeRelativeUri($targetUri).ToString()
    return [Uri]::UnescapeDataString($rel).Replace('/', '\')
}

function New-DirectoryIfMissing {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param([string]$dir)

    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
}

# Write UTF-8 (no BOM) reliably (Windows PowerShell 5.1 compatible)
function New-Utf8NoBomWriter {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param([string]$path, [bool]$append = $false)

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    if (-not $PSCmdlet.ShouldProcess($path, "Open UTF-8 (no BOM) writer")) {
        return New-Object System.IO.StreamWriter([System.IO.Stream]::Null, $utf8NoBom)
    }
    $fileMode = if ($append) { [System.IO.FileMode]::Append } else { [System.IO.FileMode]::Create }
    $fs = New-Object System.IO.FileStream($path, $fileMode, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    $sw = New-Object System.IO.StreamWriter($fs, $utf8NoBom)
    return $sw
}

function Write-Utf8NoBomFile([string]$path, [string]$content) {
    $sw = $null
    try {
        $sw = New-Utf8NoBomWriter -path $path -append:$false
        $sw.Write($content)
    }
    finally {
        if ($sw) { $sw.Dispose() }
    }
}

# ----------------------------
# Config / exclusions (v1.5.0)
# ----------------------------
# v1.5.0: 除外ルールは consult.config.json を唯一の定義元にする。
# - ConfigPath 指定時: 指定ファイルを読む。
# - ConfigPath 未指定時: tools\chatgpt\consult.config.json → .consult\consult.config.json の順に探索する。
# - config が見つからない場合は、安全のため停止する。
# NOTE: ここに固定の除外フォルダ/拡張子リストを持たない。
$DefaultConfigRelCandidates = @(
    "ai-consult-tools\chatgpt\consult.config.json",
    ".consult\consult.config.json"
)

$ExcludedFolders = @()
$ExcludedExtensions = @()
$ExcludedNamePatterns = @()
$SecretNamePatterns = @()
$AllowedToolIncludeFiles = @()

$RuleFileRel = ""
$OutRootRel = ""
$ConfigPathFull = ""
$ConfigApplied = $false

function ConvertTo-StringArray([object]$value, [string]$settingName) {
    if ($null -eq $value) { return @() }
    if ($value -is [string]) { return @([string]$value) }

    $out = New-Object System.Collections.Generic.List[string]
    if ($value -is [System.Collections.IEnumerable]) {
        foreach ($item in $value) {
            if ($null -eq $item) { continue }
            $s = [string]$item
            if (-not [string]::IsNullOrWhiteSpace($s)) { $out.Add($s.Trim()) | Out-Null }
        }
        return @($out)
    }

    throw "Invalid config value: $settingName must be a string or an array of strings."
}

function Test-ConfigProperty([object]$config, [string]$name) {
    if ($null -eq $config) { return $false }
    return @($config.PSObject.Properties.Name) -contains $name
}

function Require-ConfigProperty([object]$config, [string]$name) {
    if (-not (Test-ConfigProperty $config $name)) {
        throw "Invalid consult config: required property is missing: $name"
    }
}

function Add-UniqueStrings([string[]]$base, [string[]]$extra) {
    $set = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($item in @($base + $extra)) {
        if ([string]::IsNullOrWhiteSpace($item)) { continue }
        $s = $item.Trim()
        if ($set.Add($s)) { $out.Add($s) | Out-Null }
    }
    return @($out)
}

function Normalize-RulePathList([string[]]$items) {
    return @($items | ForEach-Object { $_.Trim().Replace('/', '\') } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Normalize-ExtensionList([string[]]$items) {
    return @($items | ForEach-Object {
        $s = $_.Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($s)) { return }
        if (-not $s.StartsWith('.')) { $s = ".$s" }
        $s
    })
}

function Resolve-RepoRelativeConfigPath([string]$repoFull, [string]$pathValue, [string]$settingName) {
    if ([string]::IsNullOrWhiteSpace($pathValue)) {
        throw "Invalid config value: $settingName must not be empty."
    }

    $candidate = $pathValue.Trim()
    if ([System.IO.Path]::IsPathRooted($candidate)) {
        $full = Resolve-FullPath $candidate
    }
    else {
        $full = Resolve-FullPath (Join-Path $repoFull $candidate)
    }

    $repoNorm = (Resolve-FullPath $repoFull).TrimEnd('\') + '\'
    $fullNorm = $full.TrimEnd('\') + '\'
    if (-not $fullNorm.StartsWith($repoNorm, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Invalid config value: $settingName must resolve under RepoRoot. Value: $pathValue"
    }

    return (ConvertTo-RelativePath $repoFull $full)
}

function Resolve-ConsultConfigPath([string]$repoFull, [string]$configPath) {
    if (-not [string]::IsNullOrWhiteSpace($configPath)) {
        $candidate = $configPath.Trim()
        if ([System.IO.Path]::IsPathRooted($candidate)) {
            $full = Resolve-FullPath $candidate
        }
        else {
            $full = Resolve-FullPath (Join-Path $repoFull $candidate)
        }

        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
            throw "ConfigPath not found: $full"
        }
        return $full
    }

    foreach ($rel in $DefaultConfigRelCandidates) {
        $candidate = Resolve-FullPath (Join-Path $repoFull $rel)
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    $candidatesText = ($DefaultConfigRelCandidates -join ', ')
    throw "consult config not found. Specify -ConfigPath or create one of: $candidatesText. You can copy tools\chatgpt\consult.config.example.json as a starting point."
}

function Apply-ConsultConfig([string]$repoFull, [string]$configPath) {
    $full = Resolve-ConsultConfigPath -repoFull $repoFull -configPath $configPath
    $json = Get-Content -LiteralPath $full -Raw -Encoding UTF8 | ConvertFrom-Json

    Require-ConfigProperty $json "outRoot"
    Require-ConfigProperty $json "ruleFile"
    Require-ConfigProperty $json "excludeFolders"
    Require-ConfigProperty $json "excludeExtensions"
    Require-ConfigProperty $json "excludeNamePatterns"
    Require-ConfigProperty $json "secretNamePatterns"
    Require-ConfigProperty $json "allowedToolIncludeFiles"

    $script:OutRootRel = Resolve-RepoRelativeConfigPath $repoFull ([string]$json.outRoot) "outRoot"
    $script:RuleFileRel = Resolve-RepoRelativeConfigPath $repoFull ([string]$json.ruleFile) "ruleFile"
    $script:ExcludedFolders = Normalize-RulePathList (ConvertTo-StringArray $json.excludeFolders "excludeFolders")
    $script:ExcludedExtensions = Normalize-ExtensionList (ConvertTo-StringArray $json.excludeExtensions "excludeExtensions")
    $script:ExcludedNamePatterns = ConvertTo-StringArray $json.excludeNamePatterns "excludeNamePatterns"
    $script:SecretNamePatterns = ConvertTo-StringArray $json.secretNamePatterns "secretNamePatterns"
    $script:AllowedToolIncludeFiles = Normalize-RulePathList (ConvertTo-StringArray $json.allowedToolIncludeFiles "allowedToolIncludeFiles")

    # Always keep the configured rule file and output root safe:
    # - ruleFile can be explicitly included even when it lives below an excluded folder.
    # - outRoot is excluded so previously generated bundles are not re-ingested.
    $script:AllowedToolIncludeFiles = Add-UniqueStrings $script:AllowedToolIncludeFiles @($script:RuleFileRel)
    $script:ExcludedFolders = Add-UniqueStrings $script:ExcludedFolders @($script:OutRootRel)
    $script:ConfigPathFull = $full
    $script:ConfigApplied = $true
}

function Test-AllowedToolIncludeFile([string]$repoFull, [string]$fileFull) {
    $rel = ConvertTo-RelativePath $repoFull $fileFull
    $relNorm = $rel.Replace('/', '\')
    return $AllowedToolIncludeFiles -icontains $relNorm
}

function Test-ExcludedByFolder([string]$repoFull, [string]$fileFull) {
    $rel = ConvertTo-RelativePath $repoFull $fileFull
    $relNorm = $rel.Replace('/', '\')
    foreach ($f in $ExcludedFolders) {
        $rule = $f.TrimEnd('\')
        if ([string]::IsNullOrWhiteSpace($rule)) { continue }

        # folder-name rule: node_modules, dist など
        if ($rule -notmatch '[\/]') {
            $segments = $relNorm.Split('\')
            if ($segments -icontains $rule) { return $true }
            continue
        }

        # repo-relative path rule: tools\chatgpt\consult_case など
        if ($relNorm.Equals($rule, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
        $prefix = $rule + '\'
        if ($relNorm.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    # 旧トップレベル shared/ だけは引き続き除外する
    if ($relNorm.Equals('shared', [System.StringComparison]::OrdinalIgnoreCase) -or $relNorm.StartsWith('shared\', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $false
}

function Test-ExcludedByExtension([string]$fileFull) {
    $ext = [System.IO.Path]::GetExtension($fileFull)
    if ([string]::IsNullOrWhiteSpace($ext)) { return $false }
    return $ExcludedExtensions -icontains $ext.ToLowerInvariant()
}

function Test-ExcludedBySecretPattern([string]$fileFull) {
    $name = [System.IO.Path]::GetFileName($fileFull)
    foreach ($pat in $SecretNamePatterns) {
        if ($name -like $pat) { return $true }
    }
    return $false
}

function Test-ExcludedByNamePattern([string]$fileFullOrName) {
    $name = [System.IO.Path]::GetFileName($fileFullOrName)
    foreach ($pat in $ExcludedNamePatterns) {
        if ($name -like $pat) { return $true }
    }
    return $false
}

function Test-IncludableFile([string]$repoFull, [string]$fileFull) {
    $isAllowedToolIncludeFile = Test-AllowedToolIncludeFile $repoFull $fileFull
    if ((-not $isAllowedToolIncludeFile) -and (Test-ExcludedByFolder $repoFull $fileFull)) { return $false }
    if (Test-ExcludedByExtension $fileFull) { return $false }
    if (Test-ExcludedBySecretPattern $fileFull) { return $false }
    if (Test-ExcludedByNamePattern $fileFull) { return $false }
    # only include regular files
    if (-not (Test-Path -LiteralPath $fileFull -PathType Leaf)) { return $false }
    return $true
}

# ----------------------------
# Grouping
# ----------------------------
$GroupMap = @{
    "php"    = @(".php", ".phtml", ".inc")
    "ts"     = @(".ts", ".tsx")
    "js"     = @(".js", ".mjs", ".cjs")
    "sql"    = @(".sql")
    "styles" = @(".css", ".scss", ".sass", ".less")
    "docs"   = @(".md", ".txt")
    "config" = @(".json", ".yml", ".yaml", ".ini", ".conf", ".htaccess")
}

function Get-Group([string]$relPath) {
    $ext = [System.IO.Path]::GetExtension($relPath).ToLowerInvariant()
    if ($relPath.EndsWith(".htaccess", [System.StringComparison]::OrdinalIgnoreCase)) { return "config" }

    foreach ($k in $GroupMap.Keys) {
        if ($GroupMap[$k] -icontains $ext) { return $k }
    }
    return "misc"
}

function Get-CodeFenceLang([string]$relPath, [string]$group) {
    switch ($group) {
        "php" { return "php" }
        "ts" { return "ts" }
        "js" { return "js" }
        "sql" { return "sql" }
        "styles" { return "css" }
        "docs" { return "" }
        "config" {
            if ($relPath.EndsWith(".json", [System.StringComparison]::OrdinalIgnoreCase)) { return "json" }
            if ($relPath.EndsWith(".yml", [System.StringComparison]::OrdinalIgnoreCase) -or $relPath.EndsWith(".yaml", [System.StringComparison]::OrdinalIgnoreCase)) { return "yaml" }
            if ($relPath.EndsWith(".ini", [System.StringComparison]::OrdinalIgnoreCase)) { return "ini" }
            if ($relPath.EndsWith(".conf", [System.StringComparison]::OrdinalIgnoreCase)) { return "" }
            if ($relPath.EndsWith(".htaccess", [System.StringComparison]::OrdinalIgnoreCase)) { return "" }
            return ""
        }
        default { return "" }
    }
}

# ----------------------------
# DocSet / Output layout
# ----------------------------
$RepoRootFull = Resolve-FullPath $RepoRoot
if (-not (Test-Path -LiteralPath $RepoRootFull -PathType Container)) {
    throw "RepoRoot not found: $RepoRootFull"
}

$jstNow = Get-JstNow
$DocSet = $jstNow.ToString("yyyyMMddHHmmss")
$GeneratedAt = $jstNow.ToString("yyyy-MM-dd HH:mm:ss zzz")

Apply-ConsultConfig -repoFull $RepoRootFull -configPath $ConfigPath

$RuleFileFull = Join-Path $RepoRootFull $RuleFileRel
$OutRootFull = Join-Path $RepoRootFull $OutRootRel

# v1.4.5: consult_case/<DocSet>_<Mode>[_<CaseName>]/<zip> を基本とする
# - 案件フォルダ（CaseDir）は ZIP が存在するため必ず残る
# - 作業用フォルダ（WorkDir: _bundle）は ZIP 作成後に既定で削除（zip-only）

$safeCase = $CaseName
if (-not [string]::IsNullOrWhiteSpace($safeCase)) {
    # フォルダ名に安全な形へ正規化（空白→_ / 許可外文字は削除）
    $safeCase = $safeCase.Trim() -replace "\s+", "_"
    $safeCase = ($safeCase -replace "[^0-9A-Za-z._-]", "")
}

$BundleLabel = "${DocSet}_${Mode}"
if (-not [string]::IsNullOrWhiteSpace($safeCase)) {
    $BundleLabel = "${BundleLabel}_${safeCase}"
}

$CaseDir = Join-Path $OutRootFull $BundleLabel
$WorkDir = Join-Path $CaseDir "_bundle"
$PartsDir = Join-Path $WorkDir "parts"

# 互換: 旧変数名（v1.4.3まで）
$BundleDir = $WorkDir
if ($Mode -ne "diff") {
    New-DirectoryIfMissing $OutRootFull
    New-DirectoryIfMissing $CaseDir
    New-DirectoryIfMissing $WorkDir
    New-DirectoryIfMissing $PartsDir
}
$IndexPath = Join-Path $WorkDir "INDEX.md"
$TreePath = Join-Path $WorkDir "TREE.md"
$ManifestPath = Join-Path $WorkDir "MANIFEST.csv"

# 運用ルール文書を必ず同梱（v1.2）
if ($Mode -ne "diff") {
    $RuleSourcePath = $RuleFileFull
    if (-not (Test-Path -LiteralPath $RuleSourcePath -PathType Leaf)) {
        throw "Required rule file not found: $RuleSourcePath"
    }
    $RuleDestPath = Join-Path $WorkDir "00_ai_consult_operation_rules.md"
    Copy-Item -LiteralPath $RuleSourcePath -Destination $RuleDestPath -Force
}

# ----------------------------
# Collect targets
# ----------------------------
function Get-RepoFile([string]$repoFull) {
    Get-ChildItem -LiteralPath $repoFull -Recurse -File -Force | ForEach-Object { $_.FullName }
}

function Convert-IncludePaths([string[]]$includePaths) {
    # Accept both (Convert-IncludePaths):
    # -IncludePaths @("common","admin")        (array)
    # -IncludePaths "common","admin"           (array-ish)
    # -IncludePaths "common,admin"             (single CSV string)
    # -IncludePaths '"common","admin"'         (single string including quotes/commas)
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($raw in $includePaths) {
        if ([string]::IsNullOrWhiteSpace($raw)) { continue }
        $s = $raw.Trim()

        # If the argument contains comma, treat it as CSV and split.
        if ($s.Contains(",")) {
            foreach ($piece in ($s -split ",")) {
                $t = $piece.Trim()
                # strip wrapping quotes if present
                if (($t.StartsWith('"') -and $t.EndsWith('"')) -or ($t.StartsWith("'") -and $t.EndsWith("'"))) {
                    $t = $t.Substring(1, $t.Length - 2).Trim()
                }
                if (-not [string]::IsNullOrWhiteSpace($t)) { $out.Add($t) | Out-Null }
            }
            continue
        }

        # strip wrapping quotes if present
        if (($s.StartsWith('"') -and $s.EndsWith('"')) -or ($s.StartsWith("'") -and $s.EndsWith("'"))) {
            $s = $s.Substring(1, $s.Length - 2).Trim()
        }
        if (-not [string]::IsNullOrWhiteSpace($s)) { $out.Add($s) | Out-Null }
    }
    return @($out)
}

#
# v1.3 / v1.3.1 include 正規化（重複除去・親子パス最適化）
#   - v1.3.1: Approved verb 対応のため関数名を Optimize-IncludeFullPaths に変更
#
function Optimize-IncludeFullPaths([string[]]$fullPaths) {

    $set = New-Object System.Collections.Generic.HashSet[string]
    foreach ($p in $fullPaths) {
        $set.Add((Resolve-FullPath $p)) | Out-Null
    }
    
    $sorted = @($set) | Sort-Object

    $final = New-Object System.Collections.Generic.List[string]
    foreach ($p in $sorted) {
        $isChild = $false
        foreach ($q in $sorted) {
            if ($p -ne $q -and $p.StartsWith($q + "", [System.StringComparison]::OrdinalIgnoreCase)) {
                $isChild = $true
                break
            }
        }
        if (-not $isChild) {
            $final.Add($p) | Out-Null
        }
    }
    return $final
}

# v1.4 include 安全化：DocSet風ディレクトリ混入の防止（既定：除外）
# - 例：20260203114422 や 20260207190010_include など
# - 例外的に取り込みたい場合は -AllowDocSetFolders を付ける
$DocSetFolderNameRegex = '^\d{14}(_repo|_include|_diff)?$'
function Test-ContainsDocSetFolder([string]$repoFull, [string]$fileFull) {
    $rel = ConvertTo-RelativePath $repoFull $fileFull
    $parts = $rel.Split('\\') | Where-Object { $_ -ne "" }
    foreach ($seg in $parts) {
        if ($seg -match $DocSetFolderNameRegex) { return $true }
    }
    return $false
}

function Resolve-IncludeTarget([string]$repoFull, [string[]]$includePaths) {
    # v1.4.1:
    # - 単一要素がスカラー string として渡る場合があるため、常に配列化して扱う
    $includeArr = @($includePaths)
    if (-not $includeArr -or $includeArr.Count -eq 0) {
        throw "IncludePaths is required for Mode=include"
    }

    # v1.4.3:
    # - ワイルドカードは今回は非対応（最小化）
    # - ファイル名のみ（パス区切りなし）指定を許可（同名複数ヒット時は停止）
    $targets = New-Object System.Collections.Generic.List[string]
    $normalized = Convert-IncludePaths $includeArr
    $skipped = New-Object System.Collections.Generic.List[string]

    foreach ($p in $normalized) {
        if ([string]::IsNullOrWhiteSpace($p)) { continue }
        $spec = $p.Trim()

        # Wildcards are NOT supported in v1.4.5
        if ($spec -match '[\*\?\[]') {
            throw "Wildcards are not supported in v1.4.5 include specs. Use explicit path or file/folder name only (no wildcards): $spec"
        }

        # v1.4.3 hotfix:
        # - "common" のようなフォルダ名指定まで「ファイル名のみ」と誤判定しない
        #   => RepoRoot 直下に実在するパス（ファイル/フォルダ）があるなら、従来通り「パス指定」として扱う
        $specIsRelativeNoSep = (-not [System.IO.Path]::IsPathRooted($spec)) -and ($spec -notmatch '[\\/]')
        $candidateAsPath = $spec
        if (-not [System.IO.Path]::IsPathRooted($candidateAsPath)) {
            $candidateAsPath = Join-Path $repoFull $candidateAsPath
        }
        $existsAsPath = (Test-Path -LiteralPath $candidateAsPath)

        $isFileNameOnly = $specIsRelativeNoSep -and (-not $existsAsPath)
        if ($isFileNameOnly) {
            # v1.4.5:
            # - フォルダ名のみ指定を許可（同名複数ヒット時は停止）
            #   例: "public_html" -> repo 配下で同名ディレクトリを検索し、一意ならその配下を取り込む
            $dirHits = @(Get-ChildItem -LiteralPath $repoFull -Recurse -Directory -Force -Filter $spec | ForEach-Object { $_.FullName })

            # Apply DocSet folder filter + repository exclusion rules (best-effort) BEFORE ambiguity check
            $dirFiltered = New-Object System.Collections.Generic.List[string]
            foreach ($d in $dirHits) {
                if (-not $AllowDocSetFolders) {
                    if (Test-ContainsDocSetFolder $repoFull $d) { continue }
                }

                # Excluded folder rules are defined in Test-IncludableFile (file-based).
                # For directory candidates, we accept them only if they contain at least one includable file.
                $hasIncludable = Get-ChildItem -LiteralPath $d -Recurse -File -Force |
                Where-Object {
                    $f = $_.FullName
                    if (-not $AllowDocSetFolders) {
                        if (Test-ContainsDocSetFolder $repoFull $f) { return $false }
                    }
                    return (Test-IncludableFile $repoFull $f)
                } |
                Select-Object -First 1

                if ($null -ne $hasIncludable) {
                    $dirFiltered.Add($d) | Out-Null
                }
            }
            $dirHits = @($dirFiltered)

            if ($dirHits.Count -gt 1) {
                $rels = $dirHits | ForEach-Object { ConvertTo-RelativePath $repoFull $_ } | Sort-Object
                $msg = "IncludeFolderName is ambiguous (multiple matches). Use explicit path include instead.`nName: $spec`nMatches:`n - " + ($rels -join "`n - ")
                throw $msg
            }
            if ($dirHits.Count -eq 1) {
                # Expand directory to files (apply filters)
                Get-ChildItem -LiteralPath $dirHits[0] -Recurse -File -Force | ForEach-Object {
                    $f = $_.FullName
                    if (-not $AllowDocSetFolders) {
                        if (Test-ContainsDocSetFolder $repoFull $f) { return }
                    }
                    if (-not (Test-IncludableFile $repoFull $f)) { return }
                    $targets.Add($f) | Out-Null
                }
                continue
            }
            # Search by exact file name under RepoRoot
            $hits = @(Get-ChildItem -LiteralPath $repoFull -Recurse -File -Force -Filter $spec | ForEach-Object { $_.FullName })

            # Apply DocSet folder filter (default: exclude) and repository exclusion rules BEFORE ambiguity check
            $filtered = New-Object System.Collections.Generic.List[string]
            foreach ($h in $hits) {
                if (-not $AllowDocSetFolders) {
                    if (Test-ContainsDocSetFolder $repoFull $h) { continue }
                }
                if (-not (Test-IncludableFile $repoFull $h)) { continue }
                $filtered.Add($h) | Out-Null
            }
            $hits = @($filtered)

            if ($hits.Count -eq 0) {
                # v1.4.1 と同様：見つからない/除外された場合は警告してスキップ
                Write-Warning "IncludeFileName not found or excluded (skipped): $spec"
                $skipped.Add($spec) | Out-Null
                continue
            }
            if ($hits.Count -gt 1) {
                $rels = $hits | ForEach-Object { ConvertTo-RelativePath $repoFull $_ } | Sort-Object
                $msg = "IncludeFileName is ambiguous (multiple matches). Use explicit path include instead.`nName: $spec`nMatches:`n - " + ($rels -join "`n - ")
                throw $msg
            }

            $targets.Add($hits[0]) | Out-Null
            continue
        }

        # Allow absolute path too; otherwise treat as repo-relative.
        $candidate = $spec
        if (-not [System.IO.Path]::IsPathRooted($candidate)) {
            $candidate = Join-Path $repoFull $candidate
        }
        # v1.4.1 仕様どおり：存在しない IncludePath は Warning でスキップ
        # NOTE: Resolve-Path(=Resolve-FullPath) は存在しないと例外になるため、先に Test-Path する
        if (-not (Test-Path -LiteralPath $candidate)) {
            # v1.4.1:
            # - 存在しない IncludePath は Warning にしてスキップ（利便性向上）
            Write-Warning "IncludePath not found (skipped): $spec ($candidate)"
            $skipped.Add($spec) | Out-Null
            continue
        }
        $full = Resolve-FullPath $candidate
        if (Test-Path -LiteralPath $full -PathType Leaf) {
            if (-not $AllowDocSetFolders) {
                if (Test-ContainsDocSetFolder $repoFull $full) { continue }
            }
            # v1.4.6+: 明示パスでも除外はスキップ扱い（0件なら停止に収束させる）
            if (-not (Test-IncludableFile $repoFull $full)) {
                Write-Warning "IncludePath is excluded by rules (skipped): $spec ($full)"
                $skipped.Add($spec) | Out-Null
                continue
            }
            $targets.Add($full) | Out-Null
        }
        elseif (Test-Path -LiteralPath $full -PathType Container) {
            Get-ChildItem -LiteralPath $full -Recurse -File -Force | ForEach-Object {
                $f = $_.FullName
                if (-not $AllowDocSetFolders) {
                    if (Test-ContainsDocSetFolder $repoFull $f) { return }
                }
                $targets.Add($f) | Out-Null
            }
        }
    }

    # v1.4.1:
    # - スキップの結果、対象が 0 件なら安全のため停止
    if ($targets.Count -eq 0) {
        $hint = ($includeArr -join ", ")
        throw "No valid IncludePaths remained after skipping missing paths / filtering. Requested: $hint"
    }

    # v1.3: 正規化（重複除去・親子パス最適化）
    # v1.3.1: Approved verb 対応（Optimize-IncludeFullPaths）
    $normalizedFull = Optimize-IncludeFullPaths $targets
    $targets = $normalizedFull

    return $targets
}

# ----------------------------
# Tree builder (included-only)
# ----------------------------
function Build-IncludedTreeLine([string[]]$relativePaths) {
    # Build a directory tree from relative paths.
    $root = @{}

    foreach ($rp in $relativePaths) {
        $parts = $rp.Replace('/', '\').Split('\') | Where-Object { $_ -ne "" }
        # NOTE: Ensure $parts is ALWAYS an array.
        # If the pipeline outputs a single string (e.g. ".editorconfig"),
        # then $parts becomes a scalar string and later indexing ($parts[$i])
        # splits it into characters (causing TREE.md to show e/ d/ i/ ...).
        $parts = @($rp.Replace('/', '\').Split('\') | Where-Object { $_ -ne "" })
        $node = $root
        for ($i = 0; $i -lt $parts.Length; $i++) {
            $name = $parts[$i]
            if ($i -eq $parts.Length - 1) {
                # file leaf marker
                if (-not $node.ContainsKey("__files__")) { $node["__files__"] = New-Object System.Collections.Generic.List[string] }
                $node["__files__"].Add($name) | Out-Null
            }
            else {
                if (-not $node.ContainsKey($name)) { $node[$name] = @{} }
                $node = $node[$name]
            }
        }
    }

    $lines = New-Object System.Collections.Generic.List[string]

    function Walk([hashtable]$n, [string]$prefix) {
        # dirs
        $dirKeys = $n.Keys | Where-Object { $_ -ne "__files__" } | Sort-Object
        foreach ($dk in $dirKeys) {
            $lines.Add("$prefix- $dk/") | Out-Null
            Walk $n[$dk] ($prefix + "  ")
        }
        # files
        if ($n.ContainsKey("__files__")) {
            $files = $n["__files__"] | Sort-Object
            foreach ($f in $files) {
                $lines.Add("$prefix- $f") | Out-Null
            }
        }
    }

    Walk $root ""
    # v1.4.2+: Write-TreeMd([string[]]) と型整合させるため、必ず配列として返す
    return @($lines)
}

# ----------------------------
# File content formatter (snapshot)
# ----------------------------
function Read-TextFileSafe([string]$path) {
    # Read as text with explicit decoding so snapshot content does not depend on host defaults.
    # - Detect BOM when present.
    # - Default to strict UTF-8 when BOM is absent.
    $bytes = [System.IO.File]::ReadAllBytes($path)
    if ($bytes.Length -eq 0) { return "" }

    $utf8Strict = New-Object System.Text.UTF8Encoding($false, $true)
    $ms = $null
    $sr = $null
    try {
        $ms = New-Object System.IO.MemoryStream(, $bytes)
        $sr = New-Object System.IO.StreamReader($ms, $utf8Strict, $true)
        return $sr.ReadToEnd()
    }
    finally {
        if ($sr) { $sr.Dispose() }
        elseif ($ms) { $ms.Dispose() }
    }
}

function Get-FileLengthSafe([string]$path, [object]$fileInfoObj) {
    # Avoid PowerShell ETS member access like $obj.Length (can throw PropertyNotFoundException in some environments)
    # Use .NET reflection and fallbacks.
    try {
        if ($fileInfoObj -is [System.IO.FileInfo]) {
            $p = $fileInfoObj.GetType().GetProperty("Length")
            if ($null -ne $p) { return [int64]$p.GetValue($fileInfoObj, $null) }
        }
    }
    catch { }

    try {
        $fi = [System.IO.FileInfo]::new($path)
        $p2 = $fi.GetType().GetProperty("Length")
        if ($null -ne $p2) { return [int64]$p2.GetValue($fi, $null) }
    }
    catch { }

    # Last resort: open stream and read length
    $fs = $null
    try {
        $fs = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        return [int64]$fs.Length
    }
    finally {
        if ($fs) { $fs.Dispose() }
    }
}

function New-FileBlock {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param([string]$repoFull, [string]$fileFull, [string]$group, [int]$maxCharsPerFile)

    $null = $PSCmdlet.ShouldProcess($fileFull, "Build file block")
    $rel = ConvertTo-RelativePath $repoFull $fileFull
    $item = Get-Item -LiteralPath $fileFull -Force -ErrorAction Stop
    if ($item -isnot [System.IO.FileInfo]) {
        throw ("New-FileBlock: Expected FileInfo but got {0}: {1}" -f $item.GetType().FullName, $fileFull)
    }
    # NOTE: Some environments throw PropertyNotFoundException on $item.Length even when Get-Item reports FileInfo.
    # To avoid skipping normal files, compute size via a fresh FileInfo instance.
    try {
        $fi = [System.IO.FileInfo]::new($fileFull)
        $fi.Refresh()
        $bytes = [int64]$fi.Length
    }
    catch {
        throw ("New-FileBlock: Failed to get file length: {0}`n  {1}" -f $fileFull, $_.Exception.Message)
    }

    $lwt = $item.LastWriteTime
    $lwtJst = ([DateTimeOffset]$lwt).ToUniversalTime().ToOffset($JstOffset).ToString("yyyy-MM-dd HH:mm:ss zzz")

    $hash = (Get-FileHash -LiteralPath $fileFull -Algorithm SHA256).Hash.ToLowerInvariant()

    # NOTE: Ensure $content is always a string.
    # Some environments can return a non-string object from Get-Content error paths,
    # which makes ".Length" access throw PropertyNotFoundException.
    $contentRaw = Read-TextFileSafe $fileFull
    if ($null -eq $contentRaw) {
        $content = ""
    }
    elseif ($contentRaw -is [string]) {
        $content = $contentRaw
    }
    else {
        $content = [string]$contentRaw
    }

    $isTruncated = $false
    $truncNote = ""

    if ($content.Length -gt $maxCharsPerFile) {
        $isTruncated = $true
        $headLen = [Math]::Floor($maxCharsPerFile * 0.6)
        $tailLen = $maxCharsPerFile - $headLen
        $head = $content.Substring(0, $headLen)
        $tail = $content.Substring($content.Length - $tailLen, $tailLen)
        $truncNote = "`n[TRUNCATED] OriginalChars=$($content.Length) KeptChars=$($maxCharsPerFile)`n"
        $content = $head + "`n... (snip) ...`n" + $tail
    }

    $lang = Get-CodeFenceLang $rel $group

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("--- BEGIN FILE ---")
    [void]$sb.AppendLine("Path: $rel")
    [void]$sb.AppendLine("Bytes: $bytes")
    [void]$sb.AppendLine("LastWriteTime(JST): $lwtJst")
    [void]$sb.AppendLine("SHA256: $hash")
    [void]$sb.AppendLine("Group: $group")
    [void]$sb.AppendLine("--- CONTENT ---")

    $fence = '```'
    if ($lang -ne "") {
        [void]$sb.AppendLine($fence + $lang)
    }
    else {
        [void]$sb.AppendLine($fence)
    }

    if ($isTruncated -and $truncNote -ne "") {
        [void]$sb.AppendLine($truncNote.TrimEnd())
    }

    [void]$sb.AppendLine($content.TrimEnd("`r", "`n"))
    [void]$sb.AppendLine($fence)
    [void]$sb.AppendLine("--- END FILE ---")
    [void]$sb.AppendLine("")

    return [pscustomobject]@{
        RelativePath     = $rel
        Bytes            = $bytes
        LastWriteTimeJst = $lwtJst
        Sha256           = $hash
        Group            = $group
        BlockText        = $sb.ToString()
        IsTruncated      = $isTruncated
    }
}

# ----------------------------
# Part writer (size split)
# ----------------------------
function New-PartState {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param([string]$partsDir, [string]$prefix, [string]$group, [int]$partNo)

    $name = "{0}_{1}_part_{2:000}.md" -f $prefix, $group, $partNo
    $path = Join-Path $partsDir $name
    $null = $PSCmdlet.ShouldProcess($path, "Create part file writer")
    $sw = New-Utf8NoBomWriter -path $path -append:$false

    return [pscustomobject]@{
        PartNo       = $partNo
        Path         = $path
        Writer       = $sw
        BytesWritten = 0
        CharsWritten = 0
        Items        = 0
    }
}

function Close-PartState($state) {
    if ($state -and $state.Writer) {
        $state.Writer.Flush()
        $state.Writer.Dispose()
    }
}

function Write-To-Part($state, [string]$text) {
    # track size roughly by utf8 byte count
    $enc = New-Object System.Text.UTF8Encoding($false)
    $b = $enc.GetByteCount($text)
    $state.Writer.Write($text)
    $state.BytesWritten += $b
    $state.CharsWritten += $text.Length
}

# ----------------------------
# Index/TREE/MANIFEST builders
# ----------------------------
function Format-CommandLine() {
    # Best-effort reconstruction (not perfect), but good for reproducibility.
    $argsList = @()
    $argsList += "-Mode $Mode"
    $argsList += "-RepoRoot `"$RepoRootFull`""
    if ($Mode -eq "include") {
        $normInc = @(Convert-IncludePaths $IncludePaths)
        if ($normInc.Count -gt 0) {
            $joined = ($normInc | ForEach-Object { "`"$_`"" }) -join ","
            $argsList += "-IncludePaths $joined"
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($ConfigPathFull)) { $argsList += "-ConfigPath `"$ConfigPathFull`"" }
    if ($AllowDocSetFolders) { $argsList += "-AllowDocSetFolders" }
    if ($KeepBundleDir) { $argsList += "-KeepBundleDir" }
    if (-not [string]::IsNullOrWhiteSpace($CaseName)) { $argsList += "-CaseName `"$CaseName`"" }

    if ($MaxBytesPerPart -ne 536870912) { $argsList += "-MaxBytesPerPart $MaxBytesPerPart" }
    if ($MaxCharsPerPart -ne 300000) { $argsList += "-MaxCharsPerPart $MaxCharsPerPart" }
    if ($MaxCharsPerFile -ne 300000) { $argsList += "-MaxCharsPerFile $MaxCharsPerFile" }

    if ($Mode -eq "diff") {
        if ($Staged) { $argsList += "-Staged" }
        if ($UnstagedOnly) { $argsList += "-UnstagedOnly" }
        if ($DiffBase) { $argsList += "-DiffBase $DiffBase" }
        if ($DiffTarget) { $argsList += "-DiffTarget $DiffTarget" }
    }

    $scriptPath = $PSCommandPath
    if (-not $scriptPath) { $scriptPath = $MyInvocation.MyCommand.Path }
    return ("pwsh -File `"$scriptPath`" " + ($argsList -join " "))
}

function Write-IndexMd([string]$path, [hashtable]$stats, [string[]]$partFiles, [string]$extraSection) {
    $cmd = Format-CommandLine
    $exFolders = ($ExcludedFolders | Sort-Object) -join ", "
    $exExts = ($ExcludedExtensions | Sort-Object) -join ", "
    $secPats = ($SecretNamePatterns | Sort-Object) -join ", "
    $exNames = ($ExcludedNamePatterns | Sort-Object) -join ", "

    $groupsLines = New-Object System.Collections.Generic.List[string]
    foreach ($k in ($GroupMap.Keys | Sort-Object)) {
        $groupsLines.Add("- ${k}: " + (($GroupMap[$k] | Sort-Object) -join " ")) | Out-Null
    }
    $groupsLines.Add("- misc: (other)") | Out-Null

    $partsLines = $partFiles | Sort-Object | ForEach-Object { "- $_" }

    # v1.4.4: CaseName は指定時のみ Meta に出す
    $caseMeta = ""
    if (-not [string]::IsNullOrWhiteSpace($CaseName)) {
        $caseMeta = "- CaseName: $CaseName`n"
    }

    $configMeta = "- ConfigPath: (default)`n- ConfigApplied: false`n"
    if ($ConfigApplied) {
        $configMeta = "- ConfigPath: $ConfigPathFull`n- ConfigApplied: true`n"
    }

    # group 別件数（Stats 用、v1.2）
    $statsGroupsLines = @()
    if ($stats.ContainsKey("GroupsText") -and $stats.GroupsText) {
        $statsGroupsLines = $stats.GroupsText -split "`n"
    }

    $statsGroupsBlock = ""
    if ($statsGroupsLines.Count -gt 0) {
        $statsGroupsBlock = (($statsGroupsLines | ForEach-Object { "  $_" }) -join "`n")
    }

    $content = @"
## 参照確定（唯一の正）

- 唯一の正：${BundleLabel}.zip
- DocSet: $DocSet
- Mode: $Mode
- 運用ルール：00_ai_consult_operation_rules.md に従ってください

---

# INDEX (DocSet=$DocSet)

このDocSetの生成物のみを唯一の正とし、それ以外の古いファイルは参照しないこと。
生成条件（除外/対象/モード/コマンドライン）を根拠とすること。

---

## Meta

- DocSet: $DocSet
- BundleLabel: $BundleLabel
$caseMeta- GeneratedAt(JST): $GeneratedAt
- RepoRoot: $RepoRootFull
- OutRoot: $OutRootFull
- RuleFile: $RuleFileFull
$configMeta- Mode: $Mode
- CommandLine: $cmd

---

## Limits

- MaxBytesPerPart: $MaxBytesPerPart
- MaxCharsPerPart: $MaxCharsPerPart
- MaxCharsPerFile: $MaxCharsPerFile

---

## Exclusions

### Excluded Folders

- $exFolders

### Excluded Extensions

- $exExts

### Excluded Name Patterns (minified etc.)

- $exNames


### Secret Patterns (excluded)

- $secPats

---

## Grouping

$($groupsLines -join "`n")

---

## Stats

- IncludedFiles: $($stats.IncludedFiles)
- SkippedFiles: $($stats.SkippedFiles)
- IncludedBytesTotal: $($stats.IncludedBytesTotal)
- Groups:
$statsGroupsBlock

---

## Output Parts

$($partsLines -join "`n")

$extraSection
"@

    Write-Utf8NoBomFile $path $content
}

function Write-TreeMd([string]$path, [string[]]$treeLines) {
    $description = "今回「含めたファイルのみ」のツリー。"
    if ($Mode -eq "map") {
        $description = "map対象ファイルのみのツリー。本文は含めず、include束候補選定用の地図として扱う。"
    }

    $content = @"
# TREE (DocSet=$DocSet)

$description

---

$($treeLines -join "`n")
"@
    Write-Utf8NoBomFile $path $content
}

function Write-ManifestCsv([string]$path, [AllowNull()][object]$rows) {
    # UTF-8 no BOM CSV
    # NOTE: $rows may be System.Collections.Generic.List[object] in map/include/diff mode.
    #       Keep this parameter as [object] so PowerShell does not try to bind the list to [object[]].
    $sw = $null
    try {
        $sw = New-Utf8NoBomWriter -path $path -append:$false
        # v1.2: mode/docset/repo_root/is_deleted を追加
        $sw.WriteLine("relative_path,bytes,last_write_time_jst,sha256,group,part_file,is_truncated,mode,docset,repo_root,is_deleted")
        foreach ($r in $rows) {
            $line = "{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10}" -f `
            (ConvertTo-CsvField $r.relative_path), `
                $r.bytes, `
            (ConvertTo-CsvField $r.last_write_time_jst), `
            (ConvertTo-CsvField $r.sha256), `
            (ConvertTo-CsvField $r.group), `
            (ConvertTo-CsvField $r.part_file), `
            ($r.is_truncated.ToString().ToLowerInvariant()), `
            (ConvertTo-CsvField $r.mode), `
            (ConvertTo-CsvField $r.docset), `
            (ConvertTo-CsvField $r.repo_root), `
            ($r.is_deleted.ToString().ToLowerInvariant())
            $sw.WriteLine($line)
        }
    }
    finally {
        if ($sw) { $sw.Dispose() }
    }
}

function ConvertTo-CsvField {
    param([AllowNull()][string]$s)
    if ($null -eq $s) { return "" }
    # CSV用の最小エスケープ（カンマ/ダブルクォート/改行がある場合のみ引用符で囲む）
    if ($s.Contains('"')) { $s = $s.Replace('"', '""') }
    if ($s.Contains(",") -or $s.Contains('"') -or $s.Contains("`n") -or $s.Contains("`r")) {
        return '"' + $s + '"'
    }
    return $s
}


# ----------------------------
# Map processing (lightweight, no full body)
# ----------------------------
function Limit-MapLines([string[]]$lines, [int]$max) {
    $items = @($lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($items.Count -le $max) { return @($items) }
    $head = @($items | Select-Object -First $max)
    return @($head + ("- ... (truncated: {0} more)" -f ($items.Count - $max)))
}

function Get-MapTextLines([string]$fileFull) {
    $ext = [System.IO.Path]::GetExtension($fileFull).ToLowerInvariant()
    $supportedExts = @(".md", ".ps1", ".php", ".ts", ".tsx", ".js", ".jsx", ".scss", ".css")
    if ($supportedExts -notcontains $ext) { return @() }

    try {
        $content = Read-TextFileSafe $fileFull
    }
    catch {
        return @("- [read-skip] $($_.Exception.Message)")
    }

    if ($null -eq $content -or $content -eq "") { return @() }

    $lines = New-Object System.Collections.Generic.List[string]

    switch ($ext) {
        ".md" {
            $matches = [regex]::Matches($content, '(?m)^(#{1,6})\s+(.+?)\s*$')
            foreach ($m in $matches) {
                $level = $m.Groups[1].Value.Length
                $title = $m.Groups[2].Value.Trim()
                $lines.Add(("- H{0}: {1}" -f $level, $title)) | Out-Null
            }
            break
        }
        ".ps1" {
            $paramMatches = [regex]::Matches($content, '(?m)^\s*(?:\[[^\]]+\]\s*)?\$([A-Za-z_][A-Za-z0-9_]*)\b')
            foreach ($m in $paramMatches) { $lines.Add(("- param: {0}" -f $m.Groups[1].Value)) | Out-Null }
            $funcMatches = [regex]::Matches($content, '(?m)^\s*function\s+([A-Za-z_][A-Za-z0-9_-]*)\b')
            foreach ($m in $funcMatches) { $lines.Add(("- function: {0}" -f $m.Groups[1].Value)) | Out-Null }
            break
        }
        ".php" {
            $typeMatches = [regex]::Matches($content, '(?m)^\s*(?:final\s+|abstract\s+)?(class|interface|trait)\s+([A-Za-z_][A-Za-z0-9_]*)\b')
            foreach ($m in $typeMatches) { $lines.Add(("- {0}: {1}" -f $m.Groups[1].Value, $m.Groups[2].Value)) | Out-Null }
            $funcMatches = [regex]::Matches($content, '(?m)^\s*(?:(?:public|protected|private)\s+)?(?:static\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\b')
            foreach ($m in $funcMatches) { $lines.Add(("- function: {0}" -f $m.Groups[1].Value)) | Out-Null }
            break
        }
        { $_ -in @(".ts", ".tsx", ".js", ".jsx") } {
            $importMatches = [regex]::Matches($content, '(?m)^\s*import\s+.*?\s+from\s+[''\"]([^''\"]+)[''\"]')
            foreach ($m in $importMatches) { $lines.Add(("- import from: {0}" -f $m.Groups[1].Value)) | Out-Null }
            $exportMatches = [regex]::Matches($content, '(?m)^\s*export\s+(?:default\s+)?(?:abstract\s+)?(class|function|const|let|var|interface|type|enum)\s+([A-Za-z_$][A-Za-z0-9_$]*)\b')
            foreach ($m in $exportMatches) { $lines.Add(("- export {0}: {1}" -f $m.Groups[1].Value, $m.Groups[2].Value)) | Out-Null }
            break
        }
        { $_ -in @(".scss", ".css") } {
            $selectorMatches = [regex]::Matches($content, '(?m)^\s*([^\r\n{};@/$][^\r\n{};]*?)\s*\{\s*$')
            foreach ($m in $selectorMatches) {
                $selector = $m.Groups[1].Value.Trim()
                if ($selector -ne "") { $lines.Add(("- selector: {0}" -f $selector)) | Out-Null }
            }
            break
        }
        default { break }
    }

    return @(Limit-MapLines -lines @($lines) -max 80)
}

function New-MapFileBlock {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param([string]$repoFull, [string]$fileFull, [string]$group)

    $null = $PSCmdlet.ShouldProcess($fileFull, "Build map file block")
    $rel = ConvertTo-RelativePath $repoFull $fileFull
    $item = Get-Item -LiteralPath $fileFull -Force -ErrorAction Stop
    if ($item -isnot [System.IO.FileInfo]) {
        throw ("New-MapFileBlock: Expected FileInfo but got {0}: {1}" -f $item.GetType().FullName, $fileFull)
    }

    $bytes = Get-FileLengthSafe -path $fileFull -fileInfoObj $item
    $lwtJst = ([DateTimeOffset]$item.LastWriteTime).ToUniversalTime().ToOffset($JstOffset).ToString("yyyy-MM-dd HH:mm:ss zzz")
    $hash = (Get-FileHash -LiteralPath $fileFull -Algorithm SHA256).Hash.ToLowerInvariant()
    $mapLines = @(Get-MapTextLines -fileFull $fileFull)
    if ($mapLines.Count -eq 0) { $mapLines = @("- (no supported headings/symbols detected)") }

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("--- BEGIN MAP FILE ---")
    [void]$sb.AppendLine("Path: $rel")
    [void]$sb.AppendLine("Bytes: $bytes")
    [void]$sb.AppendLine("LastWriteTime(JST): $lwtJst")
    [void]$sb.AppendLine("SHA256: $hash")
    [void]$sb.AppendLine("Group: $group")
    [void]$sb.AppendLine("IncludePathsCandidate: $rel")
    [void]$sb.AppendLine("--- MAP ---")
    [void]$sb.AppendLine("※ mapは本文なしの軽量地図です。具体diff作成の一次根拠にはしないでください。")
    [void]$sb.AppendLine("")
    foreach ($line in $mapLines) { [void]$sb.AppendLine($line) }
    [void]$sb.AppendLine("--- END MAP FILE ---")
    [void]$sb.AppendLine("")

    return [pscustomobject]@{
        RelativePath     = $rel
        Bytes            = $bytes
        LastWriteTimeJst = $lwtJst
        Sha256           = $hash
        Group            = $group
        BlockText        = $sb.ToString()
    }
}

function Get-MapGitSection([string]$repoFull) {
    try {
        Assert-GitAvailable
        $status = (Invoke-Git -repoFull $repoFull -gitArgs @("status", "--short"))
        $log = (Invoke-Git -repoFull $repoFull -gitArgs @("log", "--oneline", "-5"))
        if ([string]::IsNullOrWhiteSpace($status)) { $status = "(clean)" }
        if ([string]::IsNullOrWhiteSpace($log)) { $log = "(none)" }
        return @"
---

## Git Status

```text
$status
```

---

## Git Log

```text
$log
```
"@
    }
    catch {
        return @"
---

## Git Info

```text
[git-info-unavailable] $($_.Exception.Message)
```
"@
    }
}

function Invoke-Map([string]$repoFull) {
    $candidateFiles = Get-RepoFile $repoFull
    $included = New-Object System.Collections.Generic.List[object]
    foreach ($f in $candidateFiles) {
        if (Test-IncludableFile $repoFull $f) {
            $rel = ConvertTo-RelativePath $repoFull $f
            $group = Get-Group $rel
            $included.Add([pscustomobject]@{ FullPath = $f; RelativePath = $rel; Group = $group }) | Out-Null
        }
    }

    $includedSorted = @($included | Sort-Object Group, RelativePath)
    $manifestRows = New-Object System.Collections.Generic.List[object]
    $partFilesOut = New-Object System.Collections.Generic.List[string]
    $skipped = New-Object System.Collections.Generic.List[string]

    $stats = @{
        IncludedFiles      = @($includedSorted).Count
        IncludedBytesTotal = 0
        SkippedFiles       = 0
        GroupsText         = ""
    }

    $currentGroup = $null
    $state = $null
    $partNo = 1

    foreach ($it in $includedSorted) {
        if ($currentGroup -ne $it.Group) {
            if ($state) {
                Close-PartState $state
                $leaf = (Split-Path -Leaf $state.Path)
                $partFilesOut.Add(("{0} (items={1}, bytes={2})" -f $leaf, $state.Items, $state.BytesWritten)) | Out-Null
                $state = $null
            }
            $currentGroup = $it.Group
            $partNo = 1
            $state = New-PartState -partsDir $PartsDir -prefix "map" -group $currentGroup -partNo $partNo

            $header = @"
# MAP PART (DocSet=$DocSet)

- RepoRoot: $repoFull
- Mode: map
- Group: $currentGroup
- Part: $partNo
- Notice: 本文なしの軽量地図です。具体diff作成はinclude束を一次根拠にしてください。

---

"@
            Write-To-Part $state $header
        }

        if (-not (Test-Path -LiteralPath $it.FullPath -PathType Leaf)) {
            Write-Warning ("Skip non-leaf path (unexpected): {0}" -f $it.FullPath)
            continue
        }

        try {
            $blockObj = New-MapFileBlock -repoFull $repoFull -fileFull $it.FullPath -group $it.Group
        }
        catch {
            $msg = $_.Exception.Message
            $etype = $_.Exception.GetType().FullName
            Write-Warning ("Skip file due to map/meta error: {0}`n  ex={1}`n  {2}" -f $it.FullPath, $etype, $msg)
            $skipped.Add(("{0}`t{1}`t{2}" -f $it.FullPath, $etype, $msg)) | Out-Null
            continue
        }

        $text = $blockObj.BlockText
        $enc = New-Object System.Text.UTF8Encoding($false)
        $b = $enc.GetByteCount($text)
        $wouldBytes = $state.BytesWritten + $b
        $wouldChars = $state.CharsWritten + $text.Length

        if ($state.Items -gt 0 -and ($wouldBytes -gt $MaxBytesPerPart -or $wouldChars -gt $MaxCharsPerPart)) {
            Close-PartState $state
            $leaf = (Split-Path -Leaf $state.Path)
            $partFilesOut.Add(("{0} (items={1}, bytes={2})" -f $leaf, $state.Items, $state.BytesWritten)) | Out-Null

            $partNo++
            $state = New-PartState -partsDir $PartsDir -prefix "map" -group $currentGroup -partNo $partNo
            $header2 = @"
# MAP PART (DocSet=$DocSet)

- RepoRoot: $repoFull
- Mode: map
- Group: $currentGroup
- Part: $partNo
- Notice: 本文なしの軽量地図です。具体diff作成はinclude束を一次根拠にしてください。

---

"@
            Write-To-Part $state $header2
        }

        Write-To-Part $state $text
        $state.Items++
        $stats.IncludedBytesTotal += $blockObj.Bytes

        $manifestRows.Add([pscustomobject]@{
                relative_path       = $blockObj.RelativePath
                bytes               = $blockObj.Bytes
                last_write_time_jst = $blockObj.LastWriteTimeJst
                sha256              = $blockObj.Sha256
                group               = $it.Group
                part_file           = (Split-Path -Leaf $state.Path)
                is_truncated        = $false
                mode                = $Mode
                docset              = $DocSet
                repo_root           = $RepoRootFull
                is_deleted          = $false
            }) | Out-Null
    }

    if ($includedSorted.Count -gt 0) {
        $groupCounts = $includedSorted | Group-Object Group | Sort-Object Name
        $lines = @()
        foreach ($g in $groupCounts) { $lines += ("- {0}: {1} files" -f $g.Name, $g.Count) }
        $stats.GroupsText = ($lines -join "`n")
    }
    $stats.SkippedFiles = $skipped.Count

    if ($state) {
        Close-PartState $state
        $leaf = (Split-Path -Leaf $state.Path)
        $partFilesOut.Add(("{0} (items={1}, bytes={2})" -f $leaf, $state.Items, $state.BytesWritten)) | Out-Null
    }

    $skippedPath = Join-Path $WorkDir "SKIPPED.txt"
    if ($skipped.Count -gt 0) {
        Write-Utf8NoBomFile $skippedPath ("# SKIPPED (DocSet=$DocSet)`n`n" + ($skipped -join "`n"))
    }
    else {
        Write-Utf8NoBomFile $skippedPath ("# SKIPPED (DocSet=$DocSet)`n`n(none)")
    }

    $treeLines = Build-IncludedTreeLine ($manifestRows | Select-Object -ExpandProperty relative_path)
    Write-TreeMd -path $TreePath -treeLines $treeLines
    Write-ManifestCsv -path $ManifestPath -rows $manifestRows

    $mapExtra = @"
---

## Map Mode Notice

- mapは本文なしの軽量地図です。
- include束を作る対象ファイル候補の選定に使ってください。
- map束だけを根拠に、具体的なコード差分・仕様差分を作らないでください。
- 具体修正は必ずinclude束、反映後確認はdiff束を一次根拠にしてください。
$(Get-MapGitSection -repoFull $repoFull)
"@
    Write-IndexMd -path $IndexPath -stats $stats -partFiles @($partFilesOut) -extraSection $mapExtra
}

# ----------------------------
# Snapshot processing (repo/include)
# ----------------------------
function Invoke-Snapshot([string]$mode, [string]$repoFull, [string[]]$candidateFiles) {
    $included = New-Object System.Collections.Generic.List[object]
    foreach ($f in $candidateFiles) {
        if (Test-IncludableFile $repoFull $f) {
            $rel = ConvertTo-RelativePath $repoFull $f
            $group = Get-Group $rel
            $included.Add([pscustomobject]@{ FullPath = $f; RelativePath = $rel; Group = $group }) | Out-Null
        }
    }

    # Sort stable
    # Always treat as array to safely use .Count even when empty / single item
    $includedSorted = @(
        $included | Sort-Object Group, RelativePath
    )
    $manifestRows = New-Object System.Collections.Generic.List[object]

    # v1.4.5-patch: MANIFEST 重複防止（relative_path の集合）
    $manifestPathSet = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    $partFilesOut = New-Object System.Collections.Generic.List[string]
    $skipped = New-Object System.Collections.Generic.List[string]

    $stats = @{
        IncludedFiles      = @($includedSorted).Count
        IncludedBytesTotal = 0
        SkippedFiles       = 0
        GroupsText         = ""
    }

    # group -> part state
    $currentGroup = $null
    $state = $null
    $partNo = 1

    foreach ($it in $includedSorted) {
        if ($currentGroup -ne $it.Group) {
            # close previous
            if ($state) {
                Close-PartState $state
                $leaf = (Split-Path -Leaf $state.Path)
                $partFilesOut.Add(("{0} (items={1}, bytes={2})" -f $leaf, $state.Items, $state.BytesWritten)) | Out-Null
                $state = $null
            }
            $currentGroup = $it.Group
            $partNo = 1
            $state = New-PartState -partsDir $PartsDir -prefix "snapshot" -group $currentGroup -partNo $partNo

            # header for part
            $header = @"
# SNAPSHOT PART (DocSet=$DocSet)

- RepoRoot: $repoFull
- Mode: $Mode
- Group: $currentGroup
- Part: $partNo

---

"@
            Write-To-Part $state $header
        }

        # Guard: should never happen because Test-IncludableFile checks -PathType Leaf,
        # but in practice (race/deleted/special items) we may still hit non-leaf here.
        if (-not (Test-Path -LiteralPath $it.FullPath -PathType Leaf)) {
            Write-Warning ("Skip non-leaf path (unexpected): {0}" -f $it.FullPath)
            continue
        }

        try {
            $blockObj = New-FileBlock -repoFull $repoFull -fileFull $it.FullPath -group $it.Group -maxCharsPerFile $MaxCharsPerFile
        }
        catch {
            # Do not stop entire snapshot due to one problematic item.
            $t = ""
            try { $t = (Get-Item -LiteralPath $it.FullPath -Force -ErrorAction Stop).GetType().FullName } catch { $t = "get-item-failed" }
            $msg = $_.Exception.Message
            $etype = $_.Exception.GetType().FullName
            $stack = $_.ScriptStackTrace
            Write-Warning ("Skip file due to read/meta error: {0}`n  type={1}`n  ex={2}`n  {3}" -f $it.FullPath, $t, $etype, $msg)
            $skipped.Add(("{0}`t{1}`t{2}`t{3}" -f $it.FullPath, $t, $etype, $msg)) | Out-Null
            if ($stack) { $skipped.Add(("  STACK:`t{0}" -f ($stack -replace "\r?\n", " | "))) | Out-Null }
            continue
        }
        $text = $blockObj.BlockText

        # split part if needed (but keep at least one file per part)
        $enc = New-Object System.Text.UTF8Encoding($false)
        $b = $enc.GetByteCount($text)
        $wouldBytes = $state.BytesWritten + $b
        $wouldChars = $state.CharsWritten + $text.Length

        if ($state.Items -gt 0 -and ($wouldBytes -gt $MaxBytesPerPart -or $wouldChars -gt $MaxCharsPerPart)) {
            Close-PartState $state
            $leaf = (Split-Path -Leaf $state.Path)
            $partFilesOut.Add(("{0} (items={1}, bytes={2})" -f $leaf, $state.Items, $state.BytesWritten)) | Out-Null

            $partNo++
            $state = New-PartState -partsDir $PartsDir -prefix "snapshot" -group $currentGroup -partNo $partNo
            $header2 = @"
# SNAPSHOT PART (DocSet=$DocSet)

- RepoRoot: $repoFull
- Mode: $Mode
- Group: $currentGroup
- Part: $partNo

---

"@
            Write-To-Part $state $header2
        }

        Write-To-Part $state $text
        $state.Items++

        $stats.IncludedBytesTotal += $blockObj.Bytes

        $manifestRows.Add([pscustomobject]@{
                relative_path       = $blockObj.RelativePath
                bytes               = $blockObj.Bytes
                last_write_time_jst = $blockObj.LastWriteTimeJst
                sha256              = $blockObj.Sha256
                group               = $it.Group
                part_file           = (Split-Path -Leaf $state.Path)
                is_truncated        = $blockObj.IsTruncated
                mode                = $Mode
                docset              = $DocSet
                repo_root           = $RepoRootFull
                is_deleted          = $false
            }) | Out-Null
        if ($manifestPathSet) { [void]$manifestPathSet.Add($it.RelativePath) }
    }

    # group 別件数（Stats 用）
    if ($includedSorted.Count -gt 0) {
        $groupCounts = $includedSorted | Group-Object Group | Sort-Object Name
        $lines = @()
        foreach ($g in $groupCounts) {
            $lines += ("- {0}: {1} files" -f $g.Name, $g.Count)
        }
        $stats.GroupsText = ($lines -join "`n")
    }
    $stats.SkippedFiles = $skipped.Count

    # close last
    if ($state) {
        Close-PartState $state
        $leaf = (Split-Path -Leaf $state.Path)
        $partFilesOut.Add(("{0} (items={1}, bytes={2})" -f $leaf, $state.Items, $state.BytesWritten)) | Out-Null
    }

    # Finalize stats based on successful manifest rows (to keep INDEX/MANIFEST consistent)
    # NOTE: @($manifestRows) は PowerShell のバインダで "Argument types do not match" を起こし得るため、
    #       Generic List のまま扱う（ICollection として Count を参照）
    if ($null -eq $manifestRows) {
        $stats.IncludedFiles = 0
    }
    elseif ($manifestRows -is [System.Collections.ICollection]) {
        $stats.IncludedFiles = $manifestRows.Count
    }
    else {
        # fallback（通常ここには来ない想定）
        $stats.IncludedFiles = @($manifestRows).Count
    }

    # Avoid relying on Measure-Object's .Sum property (can be fragile under strict mode / type variance)
    [int64]$bytesTotal = 0
    foreach ($row in $manifestRows) {
        if ($null -eq $row) { continue }
        $b = $row.bytes
        if ($null -eq $b) { continue }
        # bytes should be numeric; coerce safely
        try { $bytesTotal += [int64]$b } catch { }
    }
    $stats.IncludedBytesTotal = $bytesTotal

    $stats.SkippedFiles = $skipped.Count

    # Write skipped list for audit
    $skippedPath = Join-Path $WorkDir "SKIPPED.txt"
    if ($skipped.Count -gt 0) {
        Write-Utf8NoBomFile $skippedPath ("# SKIPPED (DocSet=$DocSet)`n`n" + ($skipped -join "`n"))
    }
    else {
        Write-Utf8NoBomFile $skippedPath ("# SKIPPED (DocSet=$DocSet)`n`n(none)")
    }

    # TREE.md
    $treeLines = Build-IncludedTreeLine ($manifestRows | Select-Object -ExpandProperty relative_path)
    Write-TreeMd -path $TreePath -treeLines $treeLines

    # MANIFEST.csv
    Write-ManifestCsv -path $ManifestPath -rows $manifestRows

    # INDEX.md
    Write-IndexMd -path $IndexPath -stats $stats -partFiles @($partFilesOut) -extraSection ""

    return @{
        ManifestRows = $manifestRows
        PartFiles    = $partFilesOut
        Stats        = $stats
    }
}

# ----------------------------
# Diff processing
# ----------------------------
function Assert-GitAvailable() {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) { throw "git not found in PATH. Install Git or add to PATH." }
}

function Invoke-Git([string]$repoFull, [string[]]$gitArgs) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "git"
    $psi.WorkingDirectory = $repoFull
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    # NOTE: Force UTF-8 decode for git stdout/stderr to avoid mojibake on Japanese text.
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    # NOTE: Avoid quoted/oct-escaped paths like "\343\202..." in git output.
    # This stabilizes TREE/MANIFEST and exclusion matching on Windows.
    [void]$psi.ArgumentList.Add("-c")
    [void]$psi.ArgumentList.Add("core.quotepath=false")
    foreach ($a in $gitArgs) { [void]$psi.ArgumentList.Add($a) }

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    [void]$p.Start()
    $stdout = $p.StandardOutput.ReadToEnd()
    $stderr = $p.StandardError.ReadToEnd()
    $p.WaitForExit()

    if ($p.ExitCode -ne 0) { throw "git $($gitArgs -join ' ') failed (exit=$($p.ExitCode))`n$stderr" }
    return $stdout
}

function Invoke-Diff([string]$repoFull) {
    Assert-GitAvailable

    # v1.4.5: StrictMode 対策（未定義参照防止）
    $manifestPathSet = $null

    # Determine diff arguments
    $diffArgs = @("diff", "--no-color", "--no-ext-diff")
    $diffScope = $null

    # v1.4.6: 排他（推測排除）
    if ($UnstagedOnly) {
        if ($Staged) { throw "Invalid options: -UnstagedOnly cannot be used with -Staged." }
        if ($DiffBase -or $DiffTarget) { throw "Invalid options: -UnstagedOnly cannot be used with -DiffBase/-DiffTarget." }
    }

    if ($Staged) {
        $diffArgs += "--staged"
        $diffScope = "--staged"
    }
    elseif ($UnstagedOnly) {
        # v1.4.6: index vs worktree（未ステージのみ）
        # - git diff (no HEAD) compares index..worktree
        # - keep DiffArgs minimal: do NOT append "HEAD"
        $diffScope = "index..worktree"
    }
    elseif ($DiffBase -and $DiffTarget) {
        $diffArgs += $DiffBase
        $diffArgs += $DiffTarget
        $diffScope = "base..target"
    }
    elseif ($DiffBase -and (-not $DiffTarget)) {
        # allow single ref: git diff <ref>
        $diffArgs += $DiffBase
        $diffScope = "$DiffBase..worktree"
    }
    else {
        # default: HEAD vs worktree
        $diffArgs += "HEAD"
        $diffScope = "HEAD..worktree"
    }

    # name-only for changed files
    $nameArgs = $diffArgs + @("--name-only")
    $nameOnly = Invoke-Git -repoFull $repoFull -gitArgs $nameArgs
    $changedRel = @($nameOnly.Split("`n") |
        ForEach-Object { $_.Trim().Trim('"') } |
        Where-Object { $_ -ne "" } |
        ForEach-Object { $_.Replace('/', '\') })

    # Filter changed files by exclusion rules (folder/extension/secret)
    $filtered = New-Object System.Collections.Generic.List[object]
    $skipped = New-Object System.Collections.Generic.List[string]
    foreach ($rp in $changedRel) {
        $full = Join-Path $repoFull $rp
        $isAllowedToolIncludeFile = Test-AllowedToolIncludeFile $repoFull $full
        # For deleted files, file may not exist; still keep diff, but apply folder/ext/secret using rel path
        $isExcludedFolder = $false
        foreach ($f in $ExcludedFolders) {
            if ($rp.Split('\') -icontains $f) { $isExcludedFolder = $true; break }
        }
        if ((-not $isAllowedToolIncludeFile) -and $isExcludedFolder) { $skipped.Add("[excluded-folder] $rp") | Out-Null; continue }

        $ext = [System.IO.Path]::GetExtension($rp)
        if ($ext -and ($ExcludedExtensions -icontains $ext.ToLowerInvariant())) { $skipped.Add("[excluded-ext] $rp") | Out-Null; continue }

        $name = [System.IO.Path]::GetFileName($rp)
        foreach ($pat in $ExcludedNamePatterns) { if ($name -like $pat) { $skipped.Add("[excluded-name] $rp") | Out-Null; continue 2 } }
        $isSecret = $false
        foreach ($pat in $SecretNamePatterns) { if ($name -like $pat) { $isSecret = $true; break } }
        if ($isSecret) { $skipped.Add("[secret] $rp") | Out-Null; continue }

        $group = Get-Group $rp
        $filtered.Add([pscustomobject]@{ RelativePath = $rp; FullPath = $full; Group = $group }) | Out-Null
    }

    $filteredSorted = @($filtered | Sort-Object Group, RelativePath)

    # 削除ファイル一覧（is_deleted=true 用）
    $deletedFiles = @()
    # v1.4.6: rename 検出を常時有効化（-M は推定/heuristic）
    $renames = @()
    $nameStatusArgs = $diffArgs + @("-M", "--name-status")
    $nameStatus = Invoke-Git -repoFull $repoFull -gitArgs $nameStatusArgs

    foreach ($line in $nameStatus.Split("`n")) {
        $t = $line.Trim()
        if (-not $t) { continue }

        # name-status format:
        #   D<TAB>path
        #   R100<TAB>old<TAB>new   (when -M)
        $partsAll = $t.Split("`t")
        if ($partsAll.Count -lt 2) { continue }

        $status = $partsAll[0].Trim()

        if ($status.StartsWith("R")) {
            if ($partsAll.Count -ge 3) {
                $oldPath = $partsAll[1].Trim().Trim('"').Replace('/', '\')
                $newPath = $partsAll[2].Trim().Trim('"').Replace('/', '\')
                $renames += [pscustomobject]@{ Status = $status; Old = $oldPath; New = $newPath }
            }
            continue
        }

        if ($status -ne "D") { continue }

        $path = $partsAll[1].Trim()

        $rp = $path.Trim('"').Replace('/', '\')
        $full = Join-Path $repoFull $rp
        $isAllowedToolIncludeFile = Test-AllowedToolIncludeFile $repoFull $full

        # フォルダ除外
        $isExcludedFolder = $false
        foreach ($f in $ExcludedFolders) {
            if ($rp.Split('\') -icontains $f) { $isExcludedFolder = $true; break }
        }
        if ((-not $isAllowedToolIncludeFile) -and $isExcludedFolder) { continue }

        # 拡張子除外
        $ext = [System.IO.Path]::GetExtension($rp)
        if ($ext -and ($ExcludedExtensions -icontains $ext.ToLowerInvariant())) { continue }

        # 名前パターン除外
        $name = [System.IO.Path]::GetFileName($rp)
        $skipByName = $false
        foreach ($pat in $ExcludedNamePatterns) {
            if ($name -like $pat) { $skipByName = $true; break }
        }
        if ($skipByName) { continue }

        # シークレット除外
        $isSecret = $false
        foreach ($pat in $SecretNamePatterns) {
            if ($name -like $pat) { $isSecret = $true; break }
        }
        if ($isSecret) { continue }

        $deletedFiles += $rp
    }

    # v1.4.5-patch: deletedFiles は --name-only 側にも含まれるため、MANIFEST で二重計上しないよう集合化する
    $deletedSet = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($d in $deletedFiles) { [void]$deletedSet.Add($d) }

    # v1.4.2: 差分0件（例：stagedに該当なし）の場合はエラーにせずメッセージ表示
    if ($filteredSorted.Count -eq 0 -and $deletedFiles.Count -eq 0) {
        Write-Output "INFO: diff結果=0件（変更/削除ともに0）。生成物は作成しません。($($diffArgs -join ' '))"
        # 念のため：何らかの理由で空フォルダが出来ていた場合は削除する
        try {
            if (Test-Path -LiteralPath $WorkDir -PathType Container) {
                Remove-Item -LiteralPath $WorkDir -Recurse -Force
            }
            if (Test-Path -LiteralPath $CaseDir -PathType Container) {
                # 空（または _bundle のみ）なら削除
                $items = Get-ChildItem -LiteralPath $CaseDir -Force -ErrorAction SilentlyContinue
                if (-not $items -or $items.Count -eq 0) {
                    Remove-Item -LiteralPath $CaseDir -Recurse -Force
                }
            }
        }
        catch {
            Write-Warning "Cleanup skipped: $($_.Exception.Message)"
        }
        exit 0
    }

    # diff>0件の場合のみ、ここで初めて出力先を作成する（v1.4.2 方針に整合）
    New-DirectoryIfMissing $OutRootFull
    New-DirectoryIfMissing $CaseDir
    New-DirectoryIfMissing $WorkDir
    New-DirectoryIfMissing $PartsDir

    # diff>0件なら運用ルール文書を同梱（存在しない場合は警告）
    $RuleSourcePath = $RuleFileFull
    $RuleDestPath = Join-Path $WorkDir "00_ai_consult_operation_rules.md"
    if (Test-Path -LiteralPath $RuleSourcePath) {
        Copy-Item -LiteralPath $RuleSourcePath -Destination $RuleDestPath -Force
    }
    else {
        throw "Required rule file not found: $RuleSourcePath"
    }

    # NOTE: StrictMode 対策：
    # diff ループ内（例: $stats.IncludedBytesTotal += $bytes）で $stats を参照するため、
    # foreach 開始前に初期化しておく。
    $stats = @{
        IncludedFiles      = $filteredSorted.Count
        SkippedFiles       = 0
        IncludedBytesTotal = 0
        GroupsText         = ""
    }

    # Prepare output
    $DiffIndexPath = Join-Path $WorkDir "DIFF_INDEX.md"
    $partFilesOut = New-Object System.Collections.Generic.List[string]
    $manifestRows = New-Object System.Collections.Generic.List[object]
    # v1.4.5: MANIFEST 重複防止（relative_path の集合）
    $manifestPathSet = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)

    # part writers per group
    $currentGroup = $null
    $state = $null
    $partNo = 1

    $statsLines = New-Object System.Collections.Generic.List[string]
    $statsLines.Add("- DiffMode: $($diffArgs -join ' ')") | Out-Null
    $statsLines.Add("- ChangedFiles: $($filteredSorted.Count)") | Out-Null

    # Write diffs per file into group parts
    foreach ($it in $filteredSorted) {
        if ($currentGroup -ne $it.Group) {
            if ($state) {
                Close-PartState $state
                $leaf = (Split-Path -Leaf $state.Path)
                $partFilesOut.Add(("{0} (items={1}, bytes={2})" -f $leaf, $state.Items, $state.BytesWritten)) | Out-Null
                $state = $null
            }
            $currentGroup = $it.Group
            $partNo = 1
            $state = New-PartState -partsDir $PartsDir -prefix "diff" -group $currentGroup -partNo $partNo

            $header = @"
# DIFF PART (DocSet=$DocSet)

- RepoRoot: $repoFull
- Mode: diff
- DiffArgs: $($diffArgs -join ' ')
- Group: $currentGroup
- Part: $partNo

---

"@
            Write-To-Part $state $header
        }

        # Get unified diff for this file (more reliable to group)
        $fileArgs = $diffArgs + @("--", $it.RelativePath.Replace('\', '/'))
        $diffText = Invoke-Git -repoFull $repoFull -gitArgs $fileArgs

        # Compute manifest meta (file may not exist if deleted)
        $bytes = 0
        $lwtJst = ""
        $hash = ""
        if (Test-Path -LiteralPath $it.FullPath -PathType Leaf) {
            try {
                $fi = Get-Item -LiteralPath $it.FullPath
                $bytes = Get-FileLengthSafe -path $it.FullPath -fileInfoObj $fi
                # NOTE: Diff mode uses filesystem LastWriteTime (local time) formatted with offset.
                $lwtJst = ([DateTimeOffset]$fi.LastWriteTime).ToUniversalTime().ToOffset($JstOffset).ToString("yyyy-MM-dd HH:mm:ss zzz")
                $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $it.FullPath).Hash.ToLowerInvariant()
            }
            catch {
                # keep best-effort; don't fail diff output due to hash read issues
            }
        }

        $isDeleted = $false
        if ($deletedSet) { $isDeleted = $deletedSet.Contains($it.RelativePath) }
        if ($isDeleted) { $bytes = [int64]0; $lwtJst = ""; $hash = "" }

        if (-not $isDeleted) {
            $stats.IncludedBytesTotal += $bytes
        }

        $block = New-Object System.Text.StringBuilder
        [void]$block.AppendLine("--- BEGIN DIFF FILE ---")
        [void]$block.AppendLine("Path: $($it.RelativePath)")
        [void]$block.AppendLine("Group: $($it.Group)")

        $fence = '```'
        [void]$block.AppendLine("--- DIFF ---")
        [void]$block.AppendLine($fence + "diff")
        [void]$block.AppendLine($diffText.TrimEnd("`r", "`n"))
        [void]$block.AppendLine($fence)
        [void]$block.AppendLine("--- END DIFF FILE ---")
        [void]$block.AppendLine("")

        $text = $block.ToString()

        $enc = New-Object System.Text.UTF8Encoding($false)
        $b = $enc.GetByteCount($text)
        $wouldBytes = $state.BytesWritten + $b
        $wouldChars = $state.CharsWritten + $text.Length

        if ($state.Items -gt 0 -and ($wouldBytes -gt $MaxBytesPerPart -or $wouldChars -gt $MaxCharsPerPart)) {
            Close-PartState $state
            $leaf = (Split-Path -Leaf $state.Path)
            $partFilesOut.Add(("{0} (items={1}, bytes={2})" -f $leaf, $state.Items, $state.BytesWritten)) | Out-Null

            $partNo++
            $state = New-PartState -partsDir $PartsDir -prefix "diff" -group $currentGroup -partNo $partNo
            $header2 = @"
# DIFF PART (DocSet=$DocSet)

- RepoRoot: $repoFull
- Mode: diff
- DiffArgs: $($diffArgs -join ' ')
- Group: $currentGroup
- Part: $partNo

---

"@
            Write-To-Part $state $header2
        }

        $manifestRows.Add([pscustomobject]@{
                relative_path       = $it.RelativePath
                bytes               = $bytes
                last_write_time_jst = $lwtJst
                sha256              = $hash
                group               = $it.Group
                part_file           = (Split-Path -Leaf $state.Path)
                is_truncated        = $false
                mode                = $Mode
                docset              = $DocSet
                repo_root           = $RepoRootFull
                is_deleted          = $isDeleted
            }) | Out-Null
        if ($manifestPathSet) { [void]$manifestPathSet.Add($it.RelativePath) }

        Write-To-Part $state $text
        $state.Items++
    }

    # 削除ファイル（is_deleted=true）を MANIFEST に追加
    foreach ($delRel in $deletedFiles) {
        if ($manifestPathSet -and $manifestPathSet.Contains($delRel)) {
            # Already included (e.g., appeared in --name-only). Ensure single row in MANIFEST.
            continue
        }
        $deletedGroup = Get-Group $delRel

        # v1.3: 削除ファイルにも exclusion を適用
        if (Test-ExcludedByFolder $repoFull $delRel) { continue }
        if (Test-ExcludedByExtension $delRel) { continue }
        if (Test-ExcludedBySecretPattern $delRel) { continue }

        $manifestRows.Add([pscustomobject]@{
                relative_path       = $delRel
                # v1.4.2: Sum 集計で型不一致にならないよう数値に統一
                bytes               = [int64]0
                last_write_time_jst = ""
                sha256              = ""
                group               = $deletedGroup
                part_file           = ""
                is_truncated        = $false
                mode                = $Mode
                docset              = $DocSet
                repo_root           = $RepoRootFull
                is_deleted          = $true
            }) | Out-Null
        if ($manifestPathSet) { [void]$manifestPathSet.Add($delRel) }
    }

    if ($state) {
        Close-PartState $state
        $leaf = (Split-Path -Leaf $state.Path)
        $partFilesOut.Add(("{0} (items={1}, bytes={2})" -f $leaf, $state.Items, $state.BytesWritten)) | Out-Null
    }

    # DIFF_INDEX.md
    $fileListLines = @()
    if ($filteredSorted.Count -gt 0) {
        $fileListLines = @($filteredSorted | ForEach-Object { "- [$($_.Group)] $($_.RelativePath)" })
    }
    else {
        $fileListLines = @("- (none)")
    }

    $partsLines = @()
    if ($partFilesOut.Count -gt 0) {
        $partsLines = @($partFilesOut | Sort-Object | ForEach-Object { "- $_" })
    }
    else {
        $partsLines = @("- (none)")
    }

    $diffIndex = @"
# DIFF_INDEX (DocSet=$DocSet)

- DocSet: $DocSet
- GeneratedAt(JST): $GeneratedAt
- RepoRoot: $repoFull
- Mode: diff
- DiffArgs: $($diffArgs -join ' ')
- DiffScope: $diffScope
- RenameDetection: enabled (-M, heuristic)

---

## Stats

$($statsLines -join "`n")

---

## Changed Files (filtered)

$($fileListLines -join "`n")

---

## Renames (heuristic via -M)

$(
    if ($renames -and $renames.Count -gt 0) {
        (@($renames | ForEach-Object { "- $($_.Status) $($_.Old) -> $($_.New)" }) -join "`n")
    }
    else {
        "- (none)"
    }
)

---

## Output Parts

$($partsLines -join "`n")

"@
    Write-Utf8NoBomFile $DiffIndexPath $diffIndex

    # MANIFEST.csv (changed files only)
    # NOTE: diff=0件は上で exit 0 済みのため、ここに来るのは diff>0件のみ
    Write-ManifestCsv -path $ManifestPath -rows $manifestRows

    # Stats を MANIFEST ベースに更新
    # NOTE: @($manifestRows) は PowerShell のバインダで Argument types do not match を起こし得るため、
    #       ここでは配列化を一切せず、ICollection/foreach で安全に処理する。
    if ($null -eq $manifestRows) {
        $stats.IncludedFiles = 0
        $stats.IncludedBytesTotal = 0
    }
    else {
        if ($manifestRows -is [System.Collections.ICollection]) {
            $stats.IncludedFiles = $manifestRows.Count
        }
        else {
            # 万一コレクションでない場合は 1 件扱い
            $stats.IncludedFiles = 1
        }

        $sumBytes = [int64]0
        foreach ($r in $manifestRows) {
            $b = $r.bytes
            if ($null -eq $b -or $b -eq "") { $b = 0 }
            try { $sumBytes += [int64]$b } catch { }
        }
        $stats.IncludedBytesTotal = $sumBytes

        $groupCounts = $manifestRows | Group-Object group | Sort-Object Name
        $lines = @()
        foreach ($g in $groupCounts) {
            $lines += ("- {0}: {1} files" -f $g.Name, $g.Count)
        }
        $stats.GroupsText = ($lines -join "`n")
    }

    # v1.3: MANIFEST 並び順統一（配列化しない）
    $manifestRows = $manifestRows | Sort-Object group, relative_path

    # MANIFEST.csv (changed files only)
    Write-ManifestCsv -path $ManifestPath -rows $manifestRows

    # Update skipped stats + write SKIPPED.txt (diff)
    $stats.SkippedFiles = $skipped.Count
    $skippedPath = Join-Path $WorkDir "SKIPPED.txt"
    if ($skipped.Count -gt 0) {
        Write-Utf8NoBomFile $skippedPath ("# SKIPPED (DocSet=$DocSet)`n`n" + ($skipped -join "`n"))
    }
    else {
        Write-Utf8NoBomFile $skippedPath ("# SKIPPED (DocSet=$DocSet)`n`n(none)")
    }

    # Also write INDEX.md for diff mode (reuse)
    $extra = @"

---

## Diff Index

- DIFF_INDEX.md を参照（変更ファイル一覧と統計）

"@
    Write-IndexMd -path $IndexPath -stats $stats -partFiles @($partFilesOut) -extraSection $extra

    # TREE.md (changed files only)
    $treeLines = Build-IncludedTreeLine ($filteredSorted | Select-Object -ExpandProperty RelativePath)
    Write-TreeMd -path $TreePath -treeLines $treeLines
}

# ----------------------------
# Main
# ----------------------------
try {
    switch ($Mode) {
        "map" {
            Invoke-Map $RepoRootFull
            Write-Output "OK: map bundle generated at $BundleDir"
        }
        "repo" {
            $all = Get-RepoFile $RepoRootFull
            [void](Invoke-Snapshot -mode "repo" -repoFull $RepoRootFull -candidateFiles $all)
            Write-Output "OK: repo snapshot generated at $BundleDir"
        }
        "include" {
            $targets = Resolve-IncludeTarget $RepoRootFull $IncludePaths
            [void](Invoke-Snapshot -mode "include" -repoFull $RepoRootFull -candidateFiles $targets)
            Write-Output "OK: include snapshot generated at $BundleDir"
        }
        "diff" {
            Invoke-Diff $RepoRootFull

            # diff=0件ならここに来る前に exit している

            Write-Output "OK: diff bundle generated at $BundleDir"
        }
    }
}
catch {
    if ($Diag) {
        # --- Diagnostic (Stop-safe) ---
        # NOTE: Write-Error は $ErrorActionPreference='Stop' で catch 内でも停止要因になるため使わない。
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"

        $ex = $_.Exception
        Write-Host ("[DIAG] EXCEPTION TYPE: " + $ex.GetType().FullName)
        Write-Host ("[DIAG] MESSAGE       : " + $ex.Message)
        if ($ex.InnerException) {
            Write-Host ("[DIAG] INNER TYPE    : " + $ex.InnerException.GetType().FullName)
            Write-Host ("[DIAG] INNER MESSAGE : " + $ex.InnerException.Message)
        }
        if ($_.InvocationInfo) {
            Write-Host ("[DIAG] POSITION      : " + $_.InvocationInfo.PositionMessage)
        }
        if ($_.ScriptStackTrace) {
            Write-Host ("[DIAG] STACKTRACE    : " + $_.ScriptStackTrace)
        }
        try {
            $full = ($_ | Format-List * -Force | Out-String)
            Write-Host "[DIAG] ERROR RECORD (full):"
            Write-Host $full
        }
        catch {
            Write-Host ("[DIAG] Failed to render full error record: " + $_.Exception.Message)
        }

        $ErrorActionPreference = $prevEap
        exit 1
    }

    # 通常運用（元の例外位置を保ったまま返す）
    throw
}

# v1.4.4: ZIP 自動生成（標準）
# - ZIP は CaseDir 直下に保存（<BundleLabel>.zip）
# - 既定で WorkDir（_bundle）のみ削除（zip-only）
try {
    $zipPath = Join-Path $CaseDir ("{0}.zip" -f $BundleLabel)
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    # WorkDir 配下の内容を ZIP ルートにする（_bundle というフォルダ名を含めない）
    $zipItems = Join-Path $WorkDir "*"
    Compress-Archive -Path $zipItems -DestinationPath $zipPath -Force
    # 簡易検証：存在 + サイズ（0バイト等の事故を回避）
    if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
        throw "ZIP not found after compression: $zipPath"
    }
    $zipInfo = Get-Item -LiteralPath $zipPath
    if ($zipInfo.Length -lt 1024) {
        throw "ZIP too small (unexpected): $zipPath (Length=$($zipInfo.Length))"
    }

    Write-Output "ZIP created: $zipPath"

    if (-not $KeepBundleDir) {
        try {
            Remove-Item -LiteralPath $WorkDir -Recurse -Force
            Write-Output "WorkDir removed (zip-only): $WorkDir"
        }
        catch {
            Write-Warning "WorkDir removal failed (kept): $($_.Exception.Message)"
        }
    }
}
catch {
    Write-Warning "ZIP creation failed: $($_.Exception.Message)"
}

