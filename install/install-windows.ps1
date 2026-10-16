<#
.SYNOPSIS
    Install WhisperMedical on Windows with one command (no Git, Python, pip or GitHub account needed).

.DESCRIPTION
    1. checks that this is 64-bit Windows 10 or newer,
    2. reads the public release manifest (release-manifest.json) - the single source of truth for versions, addresses and checksums,
    3. downloads the small installer program of the newest VERIFIED Windows release into a temporary folder,
    4. refuses to run it unless its size and SHA-256 equal the manifest,
    5. runs it: it downloads the program and the speech model (Whisper Large-v3), checks every SHA-256, installs (Windows asks for administrator approval)
       and starts WhisperMedical,
    6. removes the temporary installer program and ends with the installer's own exit code (0 = installed).

    Exit codes: 0 installed | 2 this computer is not supported | 3 no announced Windows release is available yet | 4 the download failed or did not match its checksum |
    anything else: the exit code of the installer program.

    Only HTTPS addresses on github.com, *.githubusercontent.com and *.github.io are accepted.
    The release is announced (manifest status "ready") only after it passed the end-to-end verification AND the owner confirmed the licence notices; until then this
    script stops with exit code 3 unless -AllowUnannounced (or the environment variable WHISPERMEDICAL_ALLOW_UNANNOUNCED=1) is given - meant for testing.

.PARAMETER Gui
    Show the installer window instead of text progress in this window (the exit code is then always 0).
.PARAMETER NoLaunch
    Do not start WhisperMedical when the installation has finished (also WHISPERMEDICAL_NO_LAUNCH=1).
.PARAMETER KeepFiles
    Keep the downloaded installer program in %TEMP% (it is deleted by default).
.PARAMETER AllowUnannounced
    Install a release that passed verification but was not announced yet (also WHISPERMEDICAL_ALLOW_UNANNOUNCED=1).
.PARAMETER ManifestUrl
    The manifest address (default: the official one). Only changed by the automated tests.
#>
[CmdletBinding()]
param(
    [switch]$Gui,
    [switch]$NoLaunch,
    [switch]$KeepFiles,
    [switch]$AllowUnannounced,
    [string]$ManifestUrl = 'https://twonezerotwo-hue.github.io/whispermedical-downloads/release-manifest.json'
)

$ErrorActionPreference = 'Stop'
$script:AllowedHostSuffixes = @('github.com', '.githubusercontent.com', '.github.io')

function New-InstallError([int]$Code, [string]$Message) {
    $e = New-Object System.Exception($Message)
    $e.Data['ExitCode'] = $Code
    return $e
}

function Test-AllowedUrl([string]$Url) {
    try { $u = [Uri]$Url } catch { return $false }
    if ($env:WHISPERMEDICAL_TEST -eq '1' -and $u.Scheme -eq 'http' -and ($u.Host -eq '127.0.0.1' -or $u.Host -eq 'localhost')) { return $true }   # the automated tests talk to a local server
    if ($u.Scheme -ne 'https') { return $false }
    foreach ($s in $script:AllowedHostSuffixes) {
        if ($u.Host -eq $s.TrimStart('.') -or ($s.StartsWith('.') -and $u.Host.EndsWith($s))) { return $true }
    }
    return $false
}

function Get-WindowsEntry($Manifest, [bool]$AllowUnannounced) {
    $entry = $Manifest.windows
    if ($null -eq $entry -or $null -eq $entry.bootstrapper) {
        throw (New-InstallError 3 'The Windows download is not available yet. Please try again later.')
    }
    $product = $Manifest.product_version
    if ($product -and $entry.version -ne $product) {
        throw (New-InstallError 3 ("WhisperMedical $product for Windows is not available yet (the newest Windows build in the release list is $($entry.version)). Please try again later."))
    }
    if ($entry.status -ne 'ready' -and -not $AllowUnannounced) {
        throw (New-InstallError 3 ("WhisperMedical $($entry.version) for Windows has been built and verified but is not announced yet, so it is not offered for installation. Please try again later."))
    }
    if ($entry.status -ne 'ready' -and -not $entry.verification.passed) {
        throw (New-InstallError 3 'This Windows release has not passed its end-to-end verification yet, so it is not installed.')
    }
    return $entry
}

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Invoke-WithRetry([scriptblock]$Action, [string]$What, [int]$Tries = 5) {
    for ($i = 1; $i -le $Tries; $i++) {
        try { return & $Action } catch {
            if ($i -eq $Tries) { throw (New-InstallError 4 ("$What failed: " + $_.Exception.Message + ' Check your internet connection and run the command again.')) }
            Start-Sleep -Seconds ($i * 2)
        }
    }
}

function Install-WhisperMedical {
    param([bool]$Gui, [bool]$NoLaunch, [bool]$KeepFiles, [bool]$AllowUnannounced, [string]$ManifestUrl)

    if (-not [Environment]::Is64BitOperatingSystem) { throw (New-InstallError 2 'WhisperMedical needs 64-bit Windows 10 or 11.') }
    if ([Environment]::OSVersion.Version.Major -lt 10) { throw (New-InstallError 2 'WhisperMedical needs Windows 10 or newer.') }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    if (-not (Test-AllowedUrl $ManifestUrl)) { throw (New-InstallError 4 'The release list address is not a secure official address.') }

    Write-Host 'Checking for the latest version ...'
    $manifest = Invoke-WithRetry { Invoke-RestMethod -UseBasicParsing -Uri $ManifestUrl -TimeoutSec 60 } 'Reading the release list'
    $entry = Get-WindowsEntry $manifest $AllowUnannounced
    $boot = $entry.bootstrapper
    if (-not (Test-AllowedUrl $boot.url)) { throw (New-InstallError 4 'The installer address in the release list is not a secure official address.') }
    $gb = [Math]::Round($entry.download_bytes / 1e9, 1)
    Write-Host ("WhisperMedical $($entry.version) for Windows ($gb GB download, about 8 GB free disk space needed during installation).")

    $folder = Join-Path ([IO.Path]::GetTempPath()) 'WhisperMedicalInstall'
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    $exe = Join-Path $folder $boot.name
    Write-Host 'Downloading the installer program ...'
    Invoke-WithRetry { Invoke-WebRequest -UseBasicParsing -Uri $boot.url -OutFile $exe -TimeoutSec 300 } 'Downloading the installer program' | Out-Null
    $size = (Get-Item -LiteralPath $exe).Length
    $sha = Get-FileSha256 $exe
    if ($size -ne [int64]$boot.size -or $sha -ne ([string]$boot.sha256).ToLowerInvariant()) {
        Remove-Item -LiteralPath $exe -Force -ErrorAction SilentlyContinue
        throw (New-InstallError 4 'The downloaded installer program does not match the release list (checksum). It was deleted and NOT run.')
    }
    Write-Host 'The installer program matches its published SHA-256. Starting it ...'

    $installerArgs = @()
    if ($Gui) { $installerArgs += '--unattended' } else { $installerArgs += '--console' }
    if ($NoLaunch) { $installerArgs += '--no-launch' }
    $code = 0
    try {
        $p = Start-Process -FilePath $exe -ArgumentList $installerArgs -Wait -PassThru
        $code = [int]$p.ExitCode
    } finally {
        if (-not $KeepFiles) { Remove-Item -LiteralPath $folder -Recurse -Force -ErrorAction SilentlyContinue }
    }
    if ($code -eq 0) { Write-Host 'WhisperMedical is installed.' } else { Write-Host "The installer ended with code $code. Run this command again to continue where it stopped." }
    return $code
}

# main: only when the file is run, not when a test dot-sources it for its functions
if ($MyInvocation.InvocationName -ne '.') {
    try {
        $flagNoLaunch = $NoLaunch.IsPresent -or ($env:WHISPERMEDICAL_NO_LAUNCH -eq '1')
        $flagAllow = $AllowUnannounced.IsPresent -or ($env:WHISPERMEDICAL_ALLOW_UNANNOUNCED -eq '1')
        $result = Install-WhisperMedical -Gui $Gui.IsPresent -NoLaunch $flagNoLaunch -KeepFiles $KeepFiles.IsPresent -AllowUnannounced $flagAllow -ManifestUrl $ManifestUrl
        exit [int]$result
    } catch {
        $code = 4
        if ($_.Exception.Data.Contains('ExitCode')) { $code = [int]$_.Exception.Data['ExitCode'] }
        Write-Host ''
        Write-Host $_.Exception.Message -ForegroundColor Red
        exit $code
    }
}
