$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install it first, then rerun this script."
}

Write-Host "[gitlab-agent] installing editable user tool from: $Root"
uv tool install --editable $Root --force
if ($LASTEXITCODE -ne 0) {
    throw "uv tool install failed with exit code $LASTEXITCODE"
}

$ConfigDir = Join-Path $HOME ".config\gitlab-agent"
$ConfigFile = Join-Path $ConfigDir ".env"

New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null

if (-not (Test-Path $ConfigFile)) {
    Write-Host ""
    Write-Host "[gitlab-agent] no global config yet."
    Write-Host "Copy your working .env to:"
    Write-Host "  $ConfigFile"
    Write-Host ""
    Write-Host "Then restrict access to the current user, for example:"
    Write-Host '  $acl = Get-Acl "$HOME\.config\gitlab-agent\.env"'
    Write-Host '  $acl.SetAccessRuleProtection($true, $false)'
    Write-Host '  $rule = New-Object System.Security.AccessControl.FileSystemAccessRule([System.Security.Principal.WindowsIdentity]::GetCurrent().Name, "FullControl", "Allow")'
    Write-Host '  $acl.AddAccessRule($rule)'
    Write-Host '  Set-Acl "$HOME\.config\gitlab-agent\.env" $acl'
} else {
    Write-Host "[gitlab-agent] using existing config: $ConfigFile"
}

Write-Host ""
Write-Host "Verify from any directory:"
Write-Host "  actual-coder --help"
Write-Host "  actual-coder config"
Write-Host "  actual-coder agents"
Write-Host "  codingagent --help  # compatibility alias"
Write-Host "  gitlab-agent --help"
