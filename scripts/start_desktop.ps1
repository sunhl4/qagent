# Launch the installed DeepSeek Harness desktop shell with this repo's
# Company Agent profile environment. The shell owns profiles/desktop;
# plugins and cordis.patch.yml in that profile are the company composition.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$DshHome = Join-Path $env:USERPROFILE ".dsh"
$Python = "C:\Users\Administrator\anaconda3\envs\qc_chem\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  throw "COMPANY_AGENT_PYTHON is missing: $Python"
}

$env:DSH_HOME = $DshHome
$env:COMPANY_AGENT_DEPLOYMENT_MODE = "development"
$env:COMPANY_AGENT_PROFILE = "company-agent"
$env:COMPANY_AGENT_PRESET = "lab"
$env:COMPANY_AGENT_PYTHON = $Python
$Installed = Join-Path $env:LOCALAPPDATA "UnitQC\company-agent\runtime"
if ((Test-Path -LiteralPath (Join-Path $Installed "src\company_agent\cli.py")) -and (Test-Path -LiteralPath (Join-Path $Installed "contracts\superagent.json"))) {
  $env:COMPANY_AGENT_PYTHONPATH = Join-Path $Installed "src"
  $env:COMPANY_AGENT_CONTRACTS_DIR = Join-Path $Installed "contracts"
} else {
  $env:COMPANY_AGENT_PYTHONPATH = Join-Path $Root "src"
  $env:COMPANY_AGENT_CONTRACTS_DIR = Join-Path $Root "contracts"
}
$env:COMPANY_AGENT_DSH_VERSION = "0.2.1-rc.5"
$env:COMPANY_AGENT_PRESET_ROOT = Join-Path $DshHome ".agent-presets"
$env:COMPANY_AGENT_SKILL_ROOT = Join-Path $DshHome "skills"
$env:PYTHONUTF8 = "1"
Remove-Item Env:COMPANY_AGENT_APPROVAL_CONTEXT -ErrorAction SilentlyContinue

$PrivateEnv = "\\wsl$\Ubuntu\home\sunhl\.cache\unitqc-company-agent\runtime-dev.env"
if (Test-Path -LiteralPath $PrivateEnv) {
  foreach ($Line in Get-Content -LiteralPath $PrivateEnv) {
    $Line = $Line.TrimEnd("`r")
    if ($Line -eq "" -or $Line.StartsWith("#")) { continue }
    $Eq = $Line.IndexOf("=")
    if ($Eq -lt 1) { continue }
    $Key = $Line.Substring(0, $Eq)
    $Value = $Line.Substring($Eq + 1)
    if ($Key -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { continue }
    if (-not (Test-Path "Env:$Key")) {
      Set-Item -Path "Env:$Key" -Value $Value
    }
  }
}

$PathEntries = @(
  "$env:SystemRoot\System32",
  $env:SystemRoot,
  "C:\Users\Administrator\anaconda3\envs\qc_chem",
  "C:\Users\Administrator\anaconda3\envs\qc_chem\Library\bin",
  "C:\Users\Administrator\anaconda3\envs\qc_chem\Scripts",
  "C:\Users\Administrator\anaconda3\envs\qc_chem\Library\usr\bin",
  "C:\Users\Administrator\anaconda3\envs\qc_chem\Library\mingw-w64\bin"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$env:PATH = ($PathEntries -join ";")

$Exe = Join-Path $env:LOCALAPPDATA "Programs\DeepSeek Harness\DeepSeek Harness.exe"
if (-not (Test-Path -LiteralPath $Exe)) {
  throw "DeepSeek Harness desktop is not installed: $Exe"
}
Start-Process -FilePath $Exe
