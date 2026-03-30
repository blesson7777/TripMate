[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RemoteHost,

    [Parameter(Mandatory = $true)]
    [string]$KeyPath,

    [string]$RemoteUser = "ubuntu",
    [string]$AppUser = "",
    [string]$AppGroup = "www-data",
    [string]$RemoteAppDir = "",
    [string]$RemoteBundlePath = "/tmp/tripmate-backend.tgz",
    [string]$ServiceName = "tripmate",
    [string]$NginxSiteName = "tripmate",
    [string]$ServerName = "",
    [string]$TlsDomain = "",
    [string]$LetsEncryptEmail = "",
    [switch]$Bootstrap,
    [switch]$UploadDotEnv
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($AppUser)) {
    $AppUser = $RemoteUser
}

if ([string]::IsNullOrWhiteSpace($RemoteAppDir)) {
    $RemoteAppDir = "/home/$AppUser/tripmate-backend"
}

function Invoke-CommandChecked {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Arguments[0] $Arguments[1..($Arguments.Length - 1)]
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $($Arguments -join ' ')"
    }
}

function Get-RepoRoot {
    $path = $PSScriptRoot
    1..3 | ForEach-Object {
        $path = Split-Path -Parent $path
    }
    return $path
}

function Escape-ShellValue {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Value
    )

    return $Value.Replace("'", "'""'""'")
}

$repoRoot = Get-RepoRoot
$resolvedKeyPath = (Resolve-Path $KeyPath).Path
$remoteTarget = "$RemoteUser@$RemoteHost"

$stageDir = Join-Path ([System.IO.Path]::GetTempPath()) ("tripmate-backend-" + [guid]::NewGuid().ToString("N"))
$bundlePath = Join-Path ([System.IO.Path]::GetTempPath()) ("tripmate-backend-" + [guid]::NewGuid().ToString("N") + ".tgz")

New-Item -ItemType Directory -Path $stageDir | Out-Null

$itemsToCopy = @(
    "api",
    "attendance",
    "deploy",
    "diesel",
    "drivers",
    "fuel",
    "reports",
    "salary",
    "services",
    "static",
    "templates",
    "tripmate",
    "trips",
    "users",
    "vehicles",
    ".env.example",
    "README.md",
    "manage.py",
    "nginx_tripmate.conf",
    "requirements.txt",
    "tripmate.service"
)

try {
    foreach ($item in $itemsToCopy) {
        $sourcePath = Join-Path $repoRoot $item
        if (-not (Test-Path $sourcePath)) {
            throw "Missing repo path: $sourcePath"
        }

        Copy-Item -Path $sourcePath -Destination $stageDir -Recurse -Force
    }

    Invoke-CommandChecked -Arguments @("tar", "-czf", $bundlePath, "-C", $stageDir, ".")

    if ($Bootstrap) {
        $bootstrapScript = Join-Path $PSScriptRoot "bootstrap_ubuntu.sh"
        Invoke-CommandChecked -Arguments @("scp", "-i", $resolvedKeyPath, $bootstrapScript, "${remoteTarget}:/tmp/bootstrap_ubuntu.sh")

        $bootstrapCommand = @(
            "chmod +x /tmp/bootstrap_ubuntu.sh",
            "sudo APP_USER='$(Escape-ShellValue $AppUser)' APP_GROUP='$(Escape-ShellValue $AppGroup)' APP_DIR='$(Escape-ShellValue $RemoteAppDir)' bash /tmp/bootstrap_ubuntu.sh"
        ) -join " && "

        Invoke-CommandChecked -Arguments @("ssh", "-i", $resolvedKeyPath, $remoteTarget, $bootstrapCommand)
    }

    Invoke-CommandChecked -Arguments @("scp", "-i", $resolvedKeyPath, $bundlePath, "${remoteTarget}:${RemoteBundlePath}")

    $remoteDeployScript = Join-Path $PSScriptRoot "deploy_remote.sh"
    Invoke-CommandChecked -Arguments @("scp", "-i", $resolvedKeyPath, $remoteDeployScript, "${remoteTarget}:/tmp/deploy_remote.sh")

    if ($UploadDotEnv) {
        $dotEnvPath = Join-Path $repoRoot ".env"
        if (-not (Test-Path $dotEnvPath)) {
            throw "Cannot upload .env because it does not exist at $dotEnvPath"
        }

        Invoke-CommandChecked -Arguments @("scp", "-i", $resolvedKeyPath, $dotEnvPath, "${remoteTarget}:/tmp/tripmate.env")
    }

    $effectiveServerName = if ([string]::IsNullOrWhiteSpace($ServerName)) { $RemoteHost } else { $ServerName }

    $remoteSteps = [System.Collections.Generic.List[string]]::new()
    $remoteSteps.Add("chmod +x /tmp/deploy_remote.sh")

    if ($UploadDotEnv) {
        $remoteSteps.Add("sudo mkdir -p '$(Escape-ShellValue $RemoteAppDir)'")
        $remoteSteps.Add("sudo install -o '$(Escape-ShellValue $AppUser)' -g '$(Escape-ShellValue $AppGroup)' -m 600 /tmp/tripmate.env '$(Escape-ShellValue $RemoteAppDir)/.env'")
        $remoteSteps.Add("rm -f /tmp/tripmate.env")
    }

    $remoteSteps.Add(
        "sudo APP_USER='$(Escape-ShellValue $AppUser)' " +
        "APP_GROUP='$(Escape-ShellValue $AppGroup)' " +
        "APP_DIR='$(Escape-ShellValue $RemoteAppDir)' " +
        "RELEASE_ARCHIVE='$(Escape-ShellValue $RemoteBundlePath)' " +
        "SERVICE_NAME='$(Escape-ShellValue $ServiceName)' " +
        "NGINX_SITE_NAME='$(Escape-ShellValue $NginxSiteName)' " +
        "SERVER_NAME='$(Escape-ShellValue $effectiveServerName)' " +
        "TLS_DOMAIN='$(Escape-ShellValue $TlsDomain)' " +
        "LETSENCRYPT_EMAIL='$(Escape-ShellValue $LetsEncryptEmail)' " +
        "bash /tmp/deploy_remote.sh"
    )

    Invoke-CommandChecked -Arguments @("ssh", "-i", $resolvedKeyPath, $remoteTarget, ($remoteSteps -join " && "))
}
finally {
    if (Test-Path $stageDir) {
        Remove-Item -Path $stageDir -Recurse -Force
    }

    if (Test-Path $bundlePath) {
        Remove-Item -Path $bundlePath -Force
    }
}
