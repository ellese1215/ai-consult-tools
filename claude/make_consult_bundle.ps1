<#
make_consult_bundle.ps1
- Claude相談用スナップショット/差分バンドル生成（仕様 v1.7.0 準拠）
- Updated: 2026-05-26 00:00
- DocSet: 202605260000
Description:
  This script generates a consultation bundle for Claude based on a local Git repository.
  It supports four modes: lightweight map, full repository snapshot, partial snapshot (include), and diff.
  Output is a single combined Markdown file (split into _part1.md / _part2.md if it exceeds MaxCharsPerPart).
  No ZIP is generated. All output files are placed directly under consult_case/<BundleLabel>/.

Usage examples:
  # NOTE:
  # - 標準実行系: pwsh（PowerShell 7+）
  # - powershell.exe（Windows PowerShell 5.1）は非対応
  # - RepoRoot はあなたの環境に合わせて変更してください
  # - v1.7.0: ZIP廃止、結合MD出力（MaxCharsPerPart超過時は_part1.md/_part2.md に分割）

  # ------------------------------------------------------------
  # Mode D: map（本文なし軽量地図）
  # ------------------------------------------------------------
  pwsh -File tools\claude\make_consult_bundle.ps1 -Mode map -RepoRoot "C:\xampp\htdocs"

  # ------------------------------------------------------------
  # Mode C: repo（全体横断スナップショット）
  # ------------------------------------------------------------
  pwsh -File tools\claude\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs"

  # 設定ファイルを明示する例（未指定時は tools\claude\consult.config.json → .consult\consult.config.json の順に自動探索）
  pwsh -File tools\claude\make_consult_bundle.ps1 -Mode repo -RepoRoot "C:\xampp\htdocs" -ConfigPath ".consult\consult.config.json"

  # 複数行（読みやすさ重視）
  pwsh -File tools\claude\make_consult_bundle.ps1 `
    -Mode repo `
    -RepoRoot "C:\xampp\htdocs"

  # ------------------------------------------------------------
  # Mode A: include（範囲指定スナップショット）
  # ------------------------------------------------------------
  pwsh -File tools\claude\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "common"

  # 複数パス指定（配列）
  pwsh -File tools\claude\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "common","admin","db\schema"

  # v1.4.5: ファイル名のみ/フォルダ名のみ指定（同名複数ヒット時は停止 / ワイルドカード非対応）
  pwsh -File tools\claude\make_consult_bundle.ps1 -Mode include -RepoRoot "C:\xampp\htdocs" -IncludePaths "Navigation.php","Loader.php"

  # 複数行（読みやすさ重視）
  pwsh -File tools\claude\make_consult_bundle.ps1 `
    -Mode include `
    -RepoRoot "C:\xampp\htdocs" `
    -IncludePaths "common","admin","db\schema"

  # ------------------------------------------------------------
  # Mode B: diff（差分バンドル）
  # ------------------------------------------------------------
  # 未コミット差分（既定: HEAD vs 作業ツリー）
  pwsh -File tools\claude\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs"

  # staged 差分
  pwsh -File tools\claude\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -Staged

  # ref 間差分
  pwsh -File tools\claude\make_consult_bundle.ps1 -Mode diff -RepoRoot "C:\xampp\htdocs" -DiffBase HEAD~1 -DiffTarget HEAD
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
    [switch]$Diag,

    [int]$MaxCharsPerPart = 300000,
    [int]$MaxCharsPerFile = 300000,

    [switch]$Staged,
    [switch]$UnstagedOnly,
    [string]$DiffBase,
    [string]$DiffTarget
)

$null = $AllowDocSetFolders, $Diag, $CaseName, $ConfigPath, $MaxCharsPerPart, $MaxCharsPerFile, $Staged, $UnstagedOnly, $DiffBase, $DiffTarget
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-RequiredPwsh {
    $currentVersion = $PSVersionTable.PSVersion
    if ($null -eq $currentVersion -or $currentVersion.Major -lt 7) {
        $hostLabel = if ($PSVersionTable.PSEdition) { $PSVersionTable.PSEdition } else { "WindowsPowerShell" }
        $scriptPath = if ($PSCommandPath) { $PSCommandPath } else { "tools\claude\make_consult_bundle.ps1" }
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

# Write UTF-8 (no BOM) reliably
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
# v1.7.0: デフォルト探索パスを tools\claude\ に変更 / フォルダ改名対応
$DefaultConfigRelCandidates = @(
    "ai-consult-tools\claude\consult.config.json",
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
    throw "consult config not found. Specify -ConfigPath or create one of: $candidatesText. You can copy tools\claude\consult.config.example.json as a starting point."
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

        if ($rule -notmatch '[\/]') {
            $segments = $relNorm.Split('\')
            if ($segments -icontains $rule) { return $true }
            continue
        }

        if ($relNorm.Equals($rule, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
        $prefix = $rule + '\'
        if ($relNorm.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
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

# v1.7.0: 出力先は CaseDir 直下（_bundle 廃止）
# - CaseDir: consult_case/<DocSet>_<Mode>[_<CaseName>]/
# - WorkDir = CaseDir（_bundle なし）

$safeCase = $CaseName
if (-not [string]::IsNullOrWhiteSpace($safeCase)) {
    $safeCase = $safeCase.Trim() -replace "\s+", "_"
    $safeCase = ($safeCase -replace "[^0-9A-Za-z._-]", "")
}

$BundleLabel = "${DocSet}_${Mode}"
if (-not [string]::IsNullOrWhiteSpace($safeCase)) {
    $BundleLabel = "${BundleLabel}_${safeCase}"
}

$CaseDir = Join-Path $OutRootFull $BundleLabel
# WorkDir は CaseDir と同一（_bundle フォルダ不要）
$WorkDir = $CaseDir

# v1.7.1: INDEX.md / TREE.md / MANIFEST.csv は結合MDに統合済みのため個別出力しない

if ($Mode -ne "diff") {
    New-DirectoryIfMissing $OutRootFull
    New-DirectoryIfMissing $CaseDir
}

# ----------------------------
# Combined MD writer (v1.7.0)
# ----------------------------
# ZIP・parts ディレクトリを廃止し、全内容を単一 MD に結合する。
# MaxCharsPerPart を超える場合は _part1.md / _part2.md ... に分割する。
# 分割なし時のファイル名: <BundleLabel>.md
# 分割あり時のファイル名: <BundleLabel>_part1.md / _part2.md ...

function New-CombinedMdState {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param([int]$partNo)

    if ($partNo -eq 1 -and -not $script:NeedsSplit) {
        # 最初は単一ファイル名で開始（分割不要なら最終的にこのまま）
        $name = "$BundleLabel.md"
    }
    else {
        $name = "${BundleLabel}_part${partNo}.md"
    }
    $path = Join-Path $CaseDir $name
    $null = $PSCmdlet.ShouldProcess($path, "Create combined MD writer")
    $sw = New-Utf8NoBomWriter -path $path -append:$false

    return [pscustomobject]@{
        PartNo       = $partNo
        Path         = $path
        Name         = $name
        Writer       = $sw
        CharsWritten = 0
        Items        = 0
    }
}

# 分割が必要になった場合に単一ファイルを分割ファイルにリネームする
$script:NeedsSplit = $false

function Rename-SingleToPartOne([string]$singlePath) {
    $newPath = Join-Path (Split-Path $singlePath -Parent) "${BundleLabel}_part1.md"
    if (Test-Path -LiteralPath $singlePath) {
        Rename-Item -LiteralPath $singlePath -NewName (Split-Path $newPath -Leaf) -Force
    }
    return $newPath
}

function Close-CombinedMdState($state) {
    if ($state -and $state.Writer) {
        $state.Writer.Flush()
        $state.Writer.Dispose()
    }
}

function Write-ToCombinedMd($state, [string]$text) {
    $state.Writer.Write($text)
    $state.CharsWritten += $text.Length
}

# ----------------------------
# Collect targets
# ----------------------------
function Get-RepoFile([string]$repoFull) {
    Get-ChildItem -LiteralPath $repoFull -Recurse -File -Force | ForEach-Object { $_.FullName }
}

function Convert-IncludePaths([string[]]$includePaths) {
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($raw in $includePaths) {
        if ([string]::IsNullOrWhiteSpace($raw)) { continue }
        $s = $raw.Trim()

        if ($s.Contains(",")) {
            foreach ($piece in ($s -split ",")) {
                $t = $piece.Trim()
                if (($t.StartsWith('"') -and $t.EndsWith('"')) -or ($t.StartsWith("'") -and $t.EndsWith("'"))) {
                    $t = $t.Substring(1, $t.Length - 2).Trim()
                }
                if (-not [string]::IsNullOrWhiteSpace($t)) { $out.Add($t) | Out-Null }
            }
            continue
        }

        if (($s.StartsWith('"') -and $s.EndsWith('"')) -or ($s.StartsWith("'") -and $s.EndsWith("'"))) {
            $s = $s.Substring(1, $s.Length - 2).Trim()
        }
        if (-not [string]::IsNullOrWhiteSpace($s)) { $out.Add($s) | Out-Null }
    }
    return @($out)
}

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

$DocSetFolderNameRegex = '^\d{14}(_repo|_include|_diff|_map)?(_[A-Za-z0-9._-]+)?$'
function Test-ContainsDocSetFolder([string]$repoFull, [string]$fileFull) {
    $rel = ConvertTo-RelativePath $repoFull $fileFull
    $parts = $rel.Split('\\') | Where-Object { $_ -ne "" }
    foreach ($seg in $parts) {
        if ($seg -match $DocSetFolderNameRegex) { return $true }
    }
    return $false
}

function Resolve-IncludeTarget([string]$repoFull, [string[]]$includePaths) {
    $includeArr = @($includePaths)
    if (-not $includeArr -or $includeArr.Count -eq 0) {
        throw "IncludePaths is required for Mode=include"
    }

    $targets = New-Object System.Collections.Generic.List[string]
    $normalized = Convert-IncludePaths $includeArr
    $skipped = New-Object System.Collections.Generic.List[string]

    foreach ($p in $normalized) {
        if ([string]::IsNullOrWhiteSpace($p)) { continue }
        $spec = $p.Trim()

        if ($spec -match '[\*\?\[]') {
            throw "Wildcards are not supported in include specs. Use explicit path or file/folder name only (no wildcards): $spec"
        }

        $specIsRelativeNoSep = (-not [System.IO.Path]::IsPathRooted($spec)) -and ($spec -notmatch '[\\/]')
        $candidateAsPath = $spec
        if (-not [System.IO.Path]::IsPathRooted($candidateAsPath)) {
            $candidateAsPath = Join-Path $repoFull $candidateAsPath
        }
        $existsAsPath = (Test-Path -LiteralPath $candidateAsPath)

        $isFileNameOnly = $specIsRelativeNoSep -and (-not $existsAsPath)
        if ($isFileNameOnly) {
            $dirHits = @(Get-ChildItem -LiteralPath $repoFull -Recurse -Directory -Force -Filter $spec | ForEach-Object { $_.FullName })

            $dirFiltered = New-Object System.Collections.Generic.List[string]
            foreach ($d in $dirHits) {
                if (-not $AllowDocSetFolders) {
                    if (Test-ContainsDocSetFolder $repoFull $d) { continue }
                }

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
            $hits = @(Get-ChildItem -LiteralPath $repoFull -Recurse -File -Force -Filter $spec | ForEach-Object { $_.FullName })

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

        $candidate = $spec
        if (-not [System.IO.Path]::IsPathRooted($candidate)) {
            $candidate = Join-Path $repoFull $candidate
        }
        if (-not (Test-Path -LiteralPath $candidate)) {
            Write-Warning "IncludePath not found (skipped): $spec ($candidate)"
            $skipped.Add($spec) | Out-Null
            continue
        }
        $full = Resolve-FullPath $candidate
        if (Test-Path -LiteralPath $full -PathType Leaf) {
            if (-not $AllowDocSetFolders) {
                if (Test-ContainsDocSetFolder $repoFull $full) {
                    Write-Warning "IncludePath skipped (DocSet folder): $spec"
                    $skipped.Add($spec) | Out-Null
                    continue
                }
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

    if ($targets.Count -eq 0) {
        $hint = ($includeArr -join ", ")
        throw "No valid IncludePaths remained after skipping missing paths / filtering. Requested: $hint"
    }

    $normalizedFull = Optimize-IncludeFullPaths $targets
    $targets = $normalizedFull

    return $targets
}

# ----------------------------
# Tree builder (included-only)
# ----------------------------
function Build-IncludedTreeLine([string[]]$relativePaths) {
    $root = @{}

    foreach ($rp in $relativePaths) {
        $parts = @($rp.Replace('/', '\').Split('\') | Where-Object { $_ -ne "" })
        $node = $root
        for ($i = 0; $i -lt $parts.Length; $i++) {
            $name = $parts[$i]
            if ($i -eq $parts.Length - 1) {
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
        $dirKeys = $n.Keys | Where-Object { $_ -ne "__files__" } | Sort-Object
        foreach ($dk in $dirKeys) {
            $lines.Add("$prefix- $dk/") | Out-Null
            Walk $n[$dk] ($prefix + "  ")
        }
        if ($n.ContainsKey("__files__")) {
            $files = $n["__files__"] | Sort-Object
            foreach ($f in $files) {
                $lines.Add("$prefix- $f") | Out-Null
            }
        }
    }

    Walk $root ""
    return @($lines)
}

# ----------------------------
# File content formatter (snapshot)
# ----------------------------
function Read-TextFileSafe([string]$path) {
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
# Index/TREE/MANIFEST builders
# ----------------------------
function Format-CommandLine() {
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
    if (-not [string]::IsNullOrWhiteSpace($CaseName)) { $argsList += "-CaseName `"$CaseName`"" }

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

function Build-IndexSection($stats, $outputFiles, $extraSection) {
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

    $outputFilesLines = $outputFiles | Sort-Object | ForEach-Object { "- $_" }

    $caseMeta = ""
    if (-not [string]::IsNullOrWhiteSpace($CaseName)) {
        $caseMeta = "- CaseName: $CaseName`n"
    }

    $configMeta = "- ConfigPath: (default)`n- ConfigApplied: false`n"
    if ($ConfigApplied) {
        $configMeta = "- ConfigPath: $ConfigPathFull`n- ConfigApplied: true`n"
    }

    $statsGroupsLines = @()
    if ($stats.ContainsKey("GroupsText") -and $stats.GroupsText) {
        $statsGroupsLines = $stats.GroupsText -split "`n"
    }

    $statsGroupsBlock = ""
    if ($statsGroupsLines.Count -gt 0) {
        $statsGroupsBlock = (($statsGroupsLines | ForEach-Object { "  $_" }) -join "`n")
    }

    # v1.7.0: 唯一の正は .md（ZIP廃止）
    $primaryFile = if ($outputFiles.Count -eq 1) { $outputFiles[0] } else { $outputFiles -join " / " }

    return @"
## 参照確定（唯一の正）

- 唯一の正：$primaryFile
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

## Output Files

$($outputFilesLines -join "`n")

$extraSection
"@
}

function Build-TreeSection($treeLines) {
    $description = "今回「含めたファイルのみ」のツリー。"
    if ($Mode -eq "map") {
        $description = "map対象ファイルのみのツリー。本文は含めず、include束候補選定用の地図として扱う。"
    }

    return @"

---

# TREE (DocSet=$DocSet)

$description

---

$($treeLines -join "`n")
"@
}

function Build-ManifestSection($rows) {
    # NOTE: $rows は Generic.List[object] または object[] が渡る。
    # [object[]] で型宣言すると PowerShell バインダで "Argument types do not match" になるため、
    # 型宣言なし + foreach で安全に処理する。
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("---")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("# MANIFEST (DocSet=$DocSet)")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine('```csv')
    [void]$sb.AppendLine("relative_path,bytes,last_write_time_jst,sha256,group,is_truncated,mode,docset,is_deleted")
    if ($null -ne $rows) {
        foreach ($r in $rows) {
            if ($null -eq $r) { continue }
            $line = "{0},{1},{2},{3},{4},{5},{6},{7},{8}" -f `
            (ConvertTo-CsvField $r.relative_path), `
                $r.bytes, `
            (ConvertTo-CsvField $r.last_write_time_jst), `
            (ConvertTo-CsvField $r.sha256), `
            (ConvertTo-CsvField $r.group), `
            ($r.is_truncated.ToString().ToLowerInvariant()), `
            (ConvertTo-CsvField $r.mode), `
            (ConvertTo-CsvField $r.docset), `
            ($r.is_deleted.ToString().ToLowerInvariant())
            [void]$sb.AppendLine($line)
        }
    }
    [void]$sb.AppendLine('```')
    return $sb.ToString()
}

function ConvertTo-CsvField {
    param([AllowNull()][string]$s)
    if ($null -eq $s) { return "" }
    if ($s.Contains('"')) { $s = $s.Replace('"', '""') }
    if ($s.Contains(",") -or $s.Contains('"') -or $s.Contains("`n") -or $s.Contains("`r")) {
        return '"' + $s + '"'
    }
    return $s
}

# ----------------------------
# Combined MD output (v1.7.0)
# ----------------------------
# INDEX + TREE + MANIFEST + 本文ブロックを単一MDに結合して出力する。
# MaxCharsPerPart 超過時は新しいパートファイルに切り替える。
# 分割が発生した場合、part1 のファイル名を <BundleLabel>_part1.md にリネームする。

function Write-CombinedMd {
    # NOTE: パラメータはすべて型宣言なし（PSEnumerableBinder の型不一致回避）。
    # さらに呼び出し側も位置引数（-Name 形式なし）で渡すこと。
    param($stats, $manifestRows, $treeLines, $extraSection, $contentBlocks)

    $partNo = 1
    $script:NeedsSplit = $false
    $state = New-CombinedMdState -partNo $partNo
    $allFiles = New-Object System.Collections.Generic.List[string]
    $allFiles.Add($state.Name) | Out-Null

    # ヘッダーセクション（INDEX + TREE + MANIFEST）を先に構築
    # ファイル名はまだ確定していないので後で差し替える placeholder として空配列で生成し、
    # 最後に確定したファイル名リストで INDEX を書き直す方式は複雑になるため、
    # ここでは暫定ファイル名（後で更新しない）で出力する。
    # 実用上は添付時に確認できるため問題ない。
    $indexSection  = Build-IndexSection -stats $stats -outputFiles @("(see below)") -extraSection $extraSection
    $treeSection   = Build-TreeSection -treeLines $treeLines
    $manifestSection = Build-ManifestSection -rows $manifestRows

    $header = $indexSection + $treeSection + $manifestSection + "`n`n---`n`n# CONTENT (DocSet=$DocSet)`n`n"

    Write-ToCombinedMd $state $header

    # 本文ブロックを順番に書き出す
    foreach ($block in $contentBlocks) {
        $wouldChars = $state.CharsWritten + $block.Length

        if ($state.Items -gt 0 -and $wouldChars -gt $MaxCharsPerPart) {
            # 分割発生
            Close-CombinedMdState $state

            if (-not $script:NeedsSplit) {
                # 初めての分割：part1 へリネーム
                $script:NeedsSplit = $true
                $renamedPath = Rename-SingleToPartOne $state.Path
                # allFiles の最初のエントリを更新
                $allFiles[0] = Split-Path $renamedPath -Leaf
            }

            $partNo++
            $state = New-CombinedMdState -partNo $partNo
            $allFiles.Add($state.Name) | Out-Null

            $partHeader = "# CONTENT PART $partNo (DocSet=$DocSet)`n`n"
            Write-ToCombinedMd $state $partHeader
        }

        Write-ToCombinedMd $state $block
        $state.Items++
    }

    Close-CombinedMdState $state

    return @($allFiles)
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

``````text
$status
``````

---

## Git Log

``````text
$log
``````
"@
    }
    catch {
        return @"
---

## Git Info

``````text
[git-info-unavailable] $($_.Exception.Message)
``````
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
    $skipped = New-Object System.Collections.Generic.List[string]
    $contentBlocks = New-Object System.Collections.Generic.List[string]

    $stats = @{
        IncludedFiles      = @($includedSorted).Count
        IncludedBytesTotal = 0
        SkippedFiles       = 0
        GroupsText         = ""
    }

    foreach ($it in $includedSorted) {
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

        $contentBlocks.Add($blockObj.BlockText) | Out-Null
        $stats.IncludedBytesTotal += $blockObj.Bytes

        $manifestRows.Add([pscustomobject]@{
                relative_path       = $blockObj.RelativePath
                bytes               = $blockObj.Bytes
                last_write_time_jst = $blockObj.LastWriteTimeJst
                sha256              = $blockObj.Sha256
                group               = $it.Group
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

    # v1.7.1: SKIPPED.txt は結合MDのStats(SkippedFiles件数)に統合済みのため個別出力しない

    $treeLines = Build-IncludedTreeLine ($manifestRows | Select-Object -ExpandProperty relative_path)

    $mapExtra = @"

---

## Map Mode Notice

- mapは本文なしの軽量地図です。
- include束を作る対象ファイル候補の選定に使ってください。
- map束だけを根拠に、具体的なコード差分・仕様差分を作らないでください。
- 具体修正は必ずinclude束、反映後確認はdiff束を一次根拠にしてください。
$(Get-MapGitSection -repoFull $repoFull)
"@

    # NOTE: 名前付き引数(-xxx)を使うと PSEnumerableBinder が型不一致を起こすため位置引数で渡す
    $_wStats = $stats
    $_wManifest = $manifestRows
    $_wTree = $treeLines
    $_wExtra = $mapExtra
    $_wBlocks = $contentBlocks
    $outputFiles = Write-CombinedMd $_wStats $_wManifest $_wTree $_wExtra $_wBlocks

    Write-Output "OK: map bundle generated at $CaseDir"
    foreach ($f in $outputFiles) { Write-Output "  -> $f" }
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

    $includedSorted = @($included | Sort-Object Group, RelativePath)
    $manifestRows = New-Object System.Collections.Generic.List[object]
    $manifestPathSet = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    $skipped = New-Object System.Collections.Generic.List[string]
    $contentBlocks = New-Object System.Collections.Generic.List[string]

    $stats = @{
        IncludedFiles      = @($includedSorted).Count
        IncludedBytesTotal = 0
        SkippedFiles       = 0
        GroupsText         = ""
    }

    foreach ($it in $includedSorted) {
        if (-not (Test-Path -LiteralPath $it.FullPath -PathType Leaf)) {
            Write-Warning ("Skip non-leaf path (unexpected): {0}" -f $it.FullPath)
            continue
        }

        try {
            $blockObj = New-FileBlock -repoFull $repoFull -fileFull $it.FullPath -group $it.Group -maxCharsPerFile $MaxCharsPerFile
        }
        catch {
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

        $contentBlocks.Add($blockObj.BlockText) | Out-Null
        $stats.IncludedBytesTotal += $blockObj.Bytes

        $manifestRows.Add([pscustomobject]@{
                relative_path       = $blockObj.RelativePath
                bytes               = $blockObj.Bytes
                last_write_time_jst = $blockObj.LastWriteTimeJst
                sha256              = $blockObj.Sha256
                group               = $it.Group
                is_truncated        = $blockObj.IsTruncated
                mode                = $Mode
                docset              = $DocSet
                repo_root           = $RepoRootFull
                is_deleted          = $false
            }) | Out-Null
        if ($manifestPathSet) { [void]$manifestPathSet.Add($it.RelativePath) }
    }

    if ($includedSorted.Count -gt 0) {
        $groupCounts = $includedSorted | Group-Object Group | Sort-Object Name
        $lines = @()
        foreach ($g in $groupCounts) {
            $lines += ("- {0}: {1} files" -f $g.Name, $g.Count)
        }
        $stats.GroupsText = ($lines -join "`n")
    }

    if ($null -eq $manifestRows) {
        $stats.IncludedFiles = 0
    }
    elseif ($manifestRows -is [System.Collections.ICollection]) {
        $stats.IncludedFiles = $manifestRows.Count
    }
    else {
        $stats.IncludedFiles = @($manifestRows).Count
    }

    [int64]$bytesTotal = 0
    foreach ($row in $manifestRows) {
        if ($null -eq $row) { continue }
        $b = $row.bytes
        if ($null -eq $b) { continue }
        try { $bytesTotal += [int64]$b } catch { }
    }
    $stats.IncludedBytesTotal = $bytesTotal
    $stats.SkippedFiles = $skipped.Count

    # v1.7.1: SKIPPED.txt は結合MDのStats(SkippedFiles件数)に統合済みのため個別出力しない

    $treeLines = Build-IncludedTreeLine ($manifestRows | Select-Object -ExpandProperty relative_path)

    $_wStats = $stats
    $_wManifest = $manifestRows
    $_wTree = $treeLines
    $_wExtra = ""
    $_wBlocks = $contentBlocks
    $outputFiles = Write-CombinedMd $_wStats $_wManifest $_wTree $_wExtra $_wBlocks

    return @{
        ManifestRows = $manifestRows
        OutputFiles  = $outputFiles
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
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
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

    $manifestPathSet = $null

    $diffArgs = @("diff", "--no-color", "--no-ext-diff")
    $diffScope = $null

    if ($UnstagedOnly) {
        if ($Staged) { throw "Invalid options: -UnstagedOnly cannot be used with -Staged." }
        if ($DiffBase -or $DiffTarget) { throw "Invalid options: -UnstagedOnly cannot be used with -DiffBase/-DiffTarget." }
    }

    if ($Staged) {
        $diffArgs += "--staged"
        $diffScope = "--staged"
    }
    elseif ($UnstagedOnly) {
        $diffScope = "index..worktree"
    }
    elseif ($DiffBase -and $DiffTarget) {
        $diffArgs += $DiffBase
        $diffArgs += $DiffTarget
        $diffScope = "base..target"
    }
    elseif ($DiffBase -and (-not $DiffTarget)) {
        $diffArgs += $DiffBase
        $diffScope = "$DiffBase..worktree"
    }
    else {
        $diffArgs += "HEAD"
        $diffScope = "HEAD..worktree"
    }

    $nameArgs = $diffArgs + @("--name-only")
    $nameOnly = Invoke-Git -repoFull $repoFull -gitArgs $nameArgs
    $changedRel = @($nameOnly.Split("`n") |
        ForEach-Object { $_.Trim().Trim('"') } |
        Where-Object { $_ -ne "" } |
        ForEach-Object { $_.Replace('/', '\') })

    $filtered = New-Object System.Collections.Generic.List[object]
    $skipped = New-Object System.Collections.Generic.List[string]
    foreach ($rp in $changedRel) {
        $full = Join-Path $repoFull $rp
        $isAllowedToolIncludeFile = Test-AllowedToolIncludeFile $repoFull $full
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

    $deletedFiles = @()
    $renames = @()
    $nameStatusArgs = $diffArgs + @("-M", "--name-status")
    $nameStatus = Invoke-Git -repoFull $repoFull -gitArgs $nameStatusArgs

    foreach ($line in $nameStatus.Split("`n")) {
        $t = $line.Trim()
        if (-not $t) { continue }

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

        $isExcludedFolder = $false
        foreach ($f in $ExcludedFolders) {
            if ($rp.Split('\') -icontains $f) { $isExcludedFolder = $true; break }
        }
        if ((-not $isAllowedToolIncludeFile) -and $isExcludedFolder) { continue }

        $ext = [System.IO.Path]::GetExtension($rp)
        if ($ext -and ($ExcludedExtensions -icontains $ext.ToLowerInvariant())) { continue }

        $name = [System.IO.Path]::GetFileName($rp)
        $skipByName = $false
        foreach ($pat in $ExcludedNamePatterns) {
            if ($name -like $pat) { $skipByName = $true; break }
        }
        if ($skipByName) { continue }

        $isSecret = $false
        foreach ($pat in $SecretNamePatterns) {
            if ($name -like $pat) { $isSecret = $true; break }
        }
        if ($isSecret) { continue }

        $deletedFiles += $rp
    }

    $deletedSet = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($d in $deletedFiles) { [void]$deletedSet.Add($d) }

    if ($filteredSorted.Count -eq 0 -and $deletedFiles.Count -eq 0) {
        Write-Output "INFO: diff結果=0件（変更/削除ともに0）。生成物は作成しません。($($diffArgs -join ' '))"
        try {
            if (Test-Path -LiteralPath $CaseDir -PathType Container) {
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

    # diff>0件の場合のみ出力先を作成
    New-DirectoryIfMissing $OutRootFull
    New-DirectoryIfMissing $CaseDir

    $stats = @{
        IncludedFiles      = $filteredSorted.Count
        SkippedFiles       = 0
        IncludedBytesTotal = 0
        GroupsText         = ""
    }

    # v1.7.1: DIFF_INDEX.md 廃止（結合MDのextraSectionに統合）
    $manifestRows = New-Object System.Collections.Generic.List[object]
    $manifestPathSet = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
    $contentBlocks = New-Object System.Collections.Generic.List[string]

    $statsLines = New-Object System.Collections.Generic.List[string]
    $statsLines.Add("- DiffMode: $($diffArgs -join ' ')") | Out-Null
    $statsLines.Add("- ChangedFiles: $($filteredSorted.Count)") | Out-Null

    foreach ($it in $filteredSorted) {
        $fileArgs = $diffArgs + @("--", $it.RelativePath.Replace('\', '/'))
        $diffText = Invoke-Git -repoFull $repoFull -gitArgs $fileArgs

        $bytes = 0
        $lwtJst = ""
        $hash = ""
        if (Test-Path -LiteralPath $it.FullPath -PathType Leaf) {
            try {
                $fi = Get-Item -LiteralPath $it.FullPath
                $bytes = Get-FileLengthSafe -path $it.FullPath -fileInfoObj $fi
                $lwtJst = ([DateTimeOffset]$fi.LastWriteTime).ToUniversalTime().ToOffset($JstOffset).ToString("yyyy-MM-dd HH:mm:ss zzz")
                $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $it.FullPath).Hash.ToLowerInvariant()
            }
            catch { }
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

        $contentBlocks.Add($block.ToString()) | Out-Null

        $manifestRows.Add([pscustomobject]@{
                relative_path       = $it.RelativePath
                bytes               = $bytes
                last_write_time_jst = $lwtJst
                sha256              = $hash
                group               = $it.Group
                is_truncated        = $false
                mode                = $Mode
                docset              = $DocSet
                repo_root           = $RepoRootFull
                is_deleted          = $isDeleted
            }) | Out-Null
        if ($manifestPathSet) { [void]$manifestPathSet.Add($it.RelativePath) }
    }

    foreach ($delRel in $deletedFiles) {
        if ($manifestPathSet -and $manifestPathSet.Contains($delRel)) { continue }
        $deletedGroup = Get-Group $delRel

        if (Test-ExcludedByFolder $repoFull $delRel) { continue }
        if (Test-ExcludedByExtension $delRel) { continue }
        if (Test-ExcludedBySecretPattern $delRel) { continue }

        $manifestRows.Add([pscustomobject]@{
                relative_path       = $delRel
                bytes               = [int64]0
                last_write_time_jst = ""
                sha256              = ""
                group               = $deletedGroup
                is_truncated        = $false
                mode                = $Mode
                docset              = $DocSet
                repo_root           = $RepoRootFull
                is_deleted          = $true
            }) | Out-Null
        if ($manifestPathSet) { [void]$manifestPathSet.Add($delRel) }
    }

    $manifestRows = $manifestRows | Sort-Object group, relative_path

    if ($filteredSorted.Count -gt 0) {
        $groupCounts = $manifestRows | Where-Object { -not $_.is_deleted } | Group-Object group | Sort-Object Name
        $lines = @()
        foreach ($g in $groupCounts) { $lines += ("- {0}: {1} files" -f $g.Name, $g.Count) }
        $stats.GroupsText = ($lines -join "`n")
    }
    $stats.SkippedFiles = $skipped.Count

    # v1.7.1: SKIPPED.txt は結合MDのStats(SkippedFiles件数)に統合済みのため個別出力しない

    # v1.7.1: DIFF_INDEX は個別ファイルではなく結合MDの extraSection に埋め込む
    $fileListLines = @()
    if ($filteredSorted.Count -gt 0) {
        $fileListLines = @($filteredSorted | ForEach-Object { "- [$($_.Group)] $($_.RelativePath)" })
    }
    else {
        $fileListLines = @("- (none)")
    }

    $renamesLines = @()
    if ($renames -and $renames.Count -gt 0) {
        $renamesLines = @($renames | ForEach-Object { "- $($_.Status) $($_.Old) -> $($_.New)" })
    }
    else {
        $renamesLines = @("- (none)")
    }

    $treeLines = Build-IncludedTreeLine ($filteredSorted | Select-Object -ExpandProperty RelativePath)

    $diffExtra = @"

---

## Diff Index

- DocSet: $DocSet
- DiffArgs: $($diffArgs -join ' ')
- DiffScope: $diffScope
- RenameDetection: enabled (-M, heuristic)

### Stats

$($statsLines -join "`n")

### Changed Files (filtered)

$($fileListLines -join "`n")

### Renames (heuristic via -M)

$($renamesLines -join "`n")

"@

    $_wStats = $stats
    $_wManifest = $manifestRows
    $_wTree = $treeLines
    $_wExtra = $diffExtra
    $_wBlocks = $contentBlocks
    $outputFiles = Write-CombinedMd $_wStats $_wManifest $_wTree $_wExtra $_wBlocks

    Write-Output "OK: diff bundle generated at $CaseDir"
    foreach ($f in $outputFiles) { Write-Output "  -> $f" }
}

# ----------------------------
# Main
# ----------------------------
try {
    switch ($Mode) {
        "map" {
            Invoke-Map $RepoRootFull
        }
        "repo" {
            $all = Get-RepoFile $RepoRootFull
            $result = Invoke-Snapshot -mode "repo" -repoFull $RepoRootFull -candidateFiles $all
            Write-Output "OK: repo snapshot generated at $CaseDir"
            foreach ($f in $result.OutputFiles) { Write-Output "  -> $f" }
        }
        "include" {
            $targets = Resolve-IncludeTarget $RepoRootFull $IncludePaths
            $result = Invoke-Snapshot -mode "include" -repoFull $RepoRootFull -candidateFiles $targets
            Write-Output "OK: include snapshot generated at $CaseDir"
            foreach ($f in $result.OutputFiles) { Write-Output "  -> $f" }
        }
        "diff" {
            Invoke-Diff $RepoRootFull
        }
    }
}
catch {
    if ($Diag) {
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

    throw
}
