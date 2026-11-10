# Launch the harness checkout as a development desktop.
# The first run builds workspace artifacts. Later runs can pass -SkipBuild
# to reopen the last build without packaging an installer.
param(
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Harness = "D:\Yaozheng\deepseek-harness"
$Root = Split-Path -Parent $PSScriptRoot
$Python = "C:\Users\Administrator\anaconda3\envs\qc_chem\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  throw "COMPANY_AGENT_PYTHON is missing: $Python"
}
if (-not (Test-Path -LiteralPath (Join-Path $Harness "package.json"))) {
  throw "Harness checkout is missing: $Harness"
}

$env:Path = "C:\Program Files\nodejs;C:\Program Files\Git\cmd;C:\Windows\System32;" + $env:Path
$env:ELECTRON_MIRROR = "https://cdn.npmmirror.com/binaries/electron/"
$env:COMPANY_AGENT_DEPLOYMENT_MODE = "development"
$env:COMPANY_AGENT_PROFILE = "company-agent"
$env:COMPANY_AGENT_PRESET = "algo"
$env:COMPANY_AGENT_PYTHON = $Python
$env:COMPANY_AGENT_PYTHONPATH = Join-Path $Root "src"
$env:COMPANY_AGENT_CONTRACTS_DIR = Join-Path $Root "contracts"
$env:COMPANY_AGENT_SKILL_ROOT = Join-Path $env:USERPROFILE ".dsh\skills"
$env:COMPANY_AGENT_DSH_VERSION = "0.2.1-rc.5"
$env:DSH_HOME = Join-Path $Harness "apps\desktop\.desktop-build\development\home"
$env:PYTHONUTF8 = "1"
Remove-Item Env:COMPANY_AGENT_APPROVAL_CONTEXT -ErrorAction SilentlyContinue

# The private file lives in the Ubuntu WSL distro. Load the connection
# settings the desktop tools read. Linux runtime paths in that file
# (DSH home, port, profile) stay out so they cannot retarget this window.
# An existing process value wins.
$PrivateEnv = "\\wsl$\Ubuntu\home\sunhl\.cache\unitqc-company-agent\runtime-dev.env"
$PrivateKeys = @(
  "COMPANY_RELAY_API_KEY",
  "COMPANY_QUANTUM_PLATFORM_INVOKE_URL",
  "COMPANY_QUANTUM_PLATFORM_TOKEN",
  "COMPANY_AGENT_MANAGED_ACCESS",
  "HPC_USER",
  "HPC_HOST",
  "HPC_PORTAL",
  "UQC_CLOUD_API_KEY",
  "UQC_CLOUD_API_BASE_URL",
  "UQC_CLOUD_PORTAL",
  "UQC_CLOUD_PROBE_PYTHON",
  "COMPANY_AGENT_GITLAB_URL",
  "COMPANY_AGENT_GITLAB_TOKEN",
  "COMPANY_AGENT_GITLAB_PROJECT_ALLOWLIST",
  "COMPANY_AGENT_GITLAB_ALLOW_PLAINTEXT",
  "COMPANY_AGENT_OPEN_WPS"
)
if (Test-Path -LiteralPath $PrivateEnv) {
  foreach ($Line in Get-Content -LiteralPath $PrivateEnv -Encoding utf8) {
    $Line = $Line.TrimEnd("`r")
    if ($Line -eq "" -or $Line.StartsWith("#")) { continue }
    $Eq = $Line.IndexOf("=")
    if ($Eq -lt 1) { continue }
    $Key = $Line.Substring(0, $Eq)
    if ($PrivateKeys -notcontains $Key) { continue }
    # An empty inherited value is not a choice. The private file still fills it.
    $Current = [Environment]::GetEnvironmentVariable($Key, 'Process')
    if (-not [string]::IsNullOrWhiteSpace($Current)) { continue }
    $Value = $Line.Substring($Eq + 1)
    # A loopback invoke URL belongs to a process on the machine that wrote the
    # file. This desktop has no such listener, so keep the tool fail-closed.
    if ($Key -eq "COMPANY_QUANTUM_PLATFORM_INVOKE_URL" -and $Value -match '^https?://(127\.0\.0\.1|localhost|\[::1\])([:/]|$)') { continue }
    if ($Value -ne "") { Set-Item -Path "Env:$Key" -Value $Value }
  }
}
# This Windows desktop is the company seat. Opening a workspace file is an
# explicit WPS launch, still refused when the file association is not WPS.
if (-not (Test-Path "Env:COMPANY_AGENT_OPEN_WPS")) {
  $env:COMPANY_AGENT_OPEN_WPS = "wps"
}

function Ensure-DevCompanyProfile {
  $profileDir = Join-Path $Harness "apps\desktop\.desktop-build\development\home\profiles\desktop"
  New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
  $manifestPath = Join-Path $profileDir "package.json"
  $core = ($Root -replace '\\','/')
  $utf8 = New-Object System.Text.UTF8Encoding $false
  if (-not (Test-Path -LiteralPath $manifestPath)) {
    $json = @"
{
  "name": "dsh-profile-desktop",
  "private": true,
  "dependencies": {
    "@unitqc/company-agent-core": "file:$core/packages/company-agent-core",
    "@unitqc/company-agent-device": "file:$core/packages/company-agent-device",
    "@unitqc/company-agent-hpc": "file:$core/packages/company-agent-hpc",
    "@unitqc/company-agent-latex": "file:$core/packages/company-agent-latex",
    "@unitqc/company-agent-office": "file:$core/packages/company-agent-office",
    "@unitqc/company-agent-plan": "file:$core/packages/company-agent-plan",
    "@unitqc/company-agent-research": "file:$core/packages/company-agent-research",
    "@unitqc/company-agent-literature": "file:$core/packages/company-agent-literature",
    "@unitqc/company-agent-policy": "file:$core/packages/company-agent-policy",
    "@unitqc/company-agent-preset": "file:$core/desktop/company-agent-preset",
    "@unitqc/company-agent-quantum": "file:$core/packages/company-agent-quantum",
    "@unitqc/company-workspace-ui": "file:$core/apps/company-workspace"
  },
  "dsh": {
    "profile": {
      "bundles": [
        "@deepseek-ai/dsh-base",
        "@deepseek-ai/dsh-web-app",
        "@unitqc/company-agent-policy",
        "@unitqc/company-agent-preset",
        "@deepseek-ai/dsh-subagent-codex",
        "@deepseek-ai/dsh-experimental-plugin-market-bundle"
      ]
    }
  }
}
"@
    [System.IO.File]::WriteAllText($manifestPath, $json.Trim() + "`n", $utf8)
  }
  $raw = [System.IO.File]::ReadAllText($manifestPath)
  if ($raw -notmatch 'company-agent-research') {
    $updated = $raw -replace '("\@unitqc/company-agent-plan": "file:[^"]+",)', "`$1`n    `"@unitqc/company-agent-research`": `"file:$core/packages/company-agent-research`","
    if ($updated -eq $raw) { throw "could not add company-agent-research to the development profile" }
    [System.IO.File]::WriteAllText($manifestPath, $updated, $utf8)
    $raw = $updated
  }
  if ($raw -notmatch 'company-agent-literature') {
    $updated = $raw -replace '("\@unitqc/company-agent-research": "file:[^"]+",)', "`$1`n    `"@unitqc/company-agent-literature`": `"file:$core/packages/company-agent-literature`","
    if ($updated -eq $raw) { throw "could not add company-agent-literature to the development profile" }
    [System.IO.File]::WriteAllText($manifestPath, $updated, $utf8)
  }
  $patchPath = Join-Path $profileDir "cordis.patch.yml"
  $patchSource = Join-Path $Root "desktop\profile\cordis.patch.yml"
  if (-not (Test-Path -LiteralPath $patchSource)) {
    throw "desktop/profile/cordis.patch.yml is missing; the dev profile has no composition to copy."
  }
  Copy-Item -LiteralPath $patchSource -Destination $patchPath -Force
  $linkRoot = Join-Path $profileDir "node_modules\@unitqc"
  New-Item -ItemType Directory -Force -Path $linkRoot | Out-Null
  $links = @{
    "company-agent-core" = Join-Path $Root "packages\company-agent-core"
    "company-agent-device" = Join-Path $Root "packages\company-agent-device"
    "company-agent-hpc" = Join-Path $Root "packages\company-agent-hpc"
    "company-agent-latex" = Join-Path $Root "packages\company-agent-latex"
    "company-agent-office" = Join-Path $Root "packages\company-agent-office"
    "company-agent-plan" = Join-Path $Root "packages\company-agent-plan"
    "company-agent-research" = Join-Path $Root "packages\company-agent-research"
    "company-agent-literature" = Join-Path $Root "packages\company-agent-literature"
    "company-agent-policy" = Join-Path $Root "packages\company-agent-policy"
    "company-agent-preset" = Join-Path $Root "desktop\company-agent-preset"
    "company-agent-quantum" = Join-Path $Root "packages\company-agent-quantum"
    "company-workspace-ui" = Join-Path $Root "apps\company-workspace"
  }
  foreach ($name in $links.Keys) {
    $link = Join-Path $linkRoot $name
    if (Test-Path -LiteralPath $link) { continue }
    cmd.exe /c "mklink /J `"$link`" `"$($links[$name])`"" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "could not link $name into the development profile" }
  }
}

function Ensure-PrimaryRuntimeCache {
  $lockPath = Join-Path $Harness "scripts\primary-runtime\lock.json"
  $cache = Join-Path $Harness "apps\desktop\.desktop-build\downloads"
  New-Item -ItemType Directory -Force -Path $cache | Out-Null
  $lock = Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $win = $lock.targets.'win-x64'
  $pythonName = "cpython-$($lock.pythonVersion)+$($lock.pythonRelease)-$($win.pythonTarget)-install_only_stripped.tar.gz"
  $assets = @(
    @{
      sha = $win.nodeSha256
      url = "https://cdn.npmmirror.com/binaries/node/v$($lock.nodeVersion)/node-v$($lock.nodeVersion)-win-x64.zip"
    }
    @{
      sha = $win.pythonSha256
      url = "https://cdn.npmmirror.com/binaries/python-build-standalone/$($lock.pythonRelease)/$([uri]::EscapeDataString($pythonName))"
    }
  )
  foreach ($wheel in @($win.wheels + $lock.wheels)) {
    $assets += @{
      sha = $wheel.sha256
      url = ($wheel.url -replace '^https://files\.pythonhosted\.org', 'https://pypi.tuna.tsinghua.edu.cn')
    }
  }
  foreach ($asset in $assets) {
    $dest = Join-Path $cache $asset.sha
    if (Test-Path -LiteralPath $dest) {
      $have = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash
      if ($have -eq $asset.sha) { continue }
      Remove-Item -LiteralPath $dest -Force
    }
    $part = "$dest.partial"
    curl.exe -fL --retry 8 --retry-all-errors -o $part $asset.url
    if ($LASTEXITCODE -ne 0) { throw "runtime download failed: $($asset.url)" }
    $have = (Get-FileHash -LiteralPath $part -Algorithm SHA256).Hash
    if ($have -ne $asset.sha) { throw "runtime checksum mismatch: $($asset.url)" }
    Move-Item -LiteralPath $part -Destination $dest
  }
}

Ensure-DevCompanyProfile
Ensure-PrimaryRuntimeCache
Set-Location $Harness
function Invoke-Pnpm {
  corepack pnpm @args
  if ($LASTEXITCODE -ne 0) { throw "pnpm exited with $LASTEXITCODE" }
}
if (-not $SkipBuild) {
  Invoke-Pnpm run build:artifacts
  Invoke-Pnpm --filter @deepseek-ai/dsh-desktop run build
}
if ($env:COMPANY_AGENT_MANAGED_ACCESS -eq "1") {
  $env:PYTHONPATH = Join-Path $Root "src"
  $env:COMPANY_AGENT_HPC_VIA_WSL = "1"
  $Command = Join-Path $env:SystemRoot "System32\cmd.exe"
  & $Python -P -m company_agent.access_runtime -- $Command /d /s /c "corepack pnpm --filter @deepseek-ai/dsh-desktop run start"
  if ($LASTEXITCODE -ne 0) { throw "desktop exited with $LASTEXITCODE" }
} else {
  Invoke-Pnpm run start:desktop
}
