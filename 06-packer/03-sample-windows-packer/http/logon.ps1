<#
# Upstream Author:
#
#     Canonical Ltd.
#
# Copyright:
#
#     (c) 2014-2023 Canonical Ltd.
#
# Licence:
#
# If you have an executed agreement with a Canonical group company which
# includes a licence to this software, your use of this software is governed
# by that agreement.  Otherwise, the following applies:
#
# Canonical Ltd. hereby grants to you a world-wide, non-exclusive,
# non-transferable, revocable, perpetual (unless revoked) licence, to (i) use
# this software in connection with Canonical's MAAS software to install Windows
# in non-production environments and (ii) to make a reasonable number of copies
# of this software for backup and installation purposes.  You may not: use,
# copy, modify, disassemble, decompile, reverse engineer, or distribute the
# software except as expressly permitted in this licence; permit access to the
# software to any third party other than those acting on your behalf; or use
# this software in connection with a production environment.
#
# CANONICAL LTD. MAKES THIS SOFTWARE AVAILABLE "AS-IS".  CANONICAL  LTD. MAKES
# NO REPRESENTATIONS OR WARRANTIES OF ANY KIND, WHETHER ORAL OR WRITTEN,
# WHETHER EXPRESS, IMPLIED, OR ARISING BY STATUTE, CUSTOM, COURSE OF DEALING
# OR TRADE USAGE, WITH RESPECT TO THIS SOFTWARE.  CANONICAL LTD. SPECIFICALLY
# DISCLAIMS ANY AND ALL IMPLIED WARRANTIES OR CONDITIONS OF TITLE, SATISFACTORY
# QUALITY, MERCHANTABILITY, SATISFACTORINESS, FITNESS FOR A PARTICULAR PURPOSE
# AND NON-INFRINGEMENT.
#
# IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING WILL
# CANONICAL LTD. OR ANY OF ITS AFFILIATES, BE LIABLE TO YOU FOR DAMAGES,
# INCLUDING ANY GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING
# OUT OF THE USE OR INABILITY TO USE THIS SOFTWARE (INCLUDING BUT NOT LIMITED
# TO LOSS OF DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU
# OR THIRD PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER
# PROGRAMS), EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGES.
#>

param(
    [Parameter()]
    [switch]$RunPowershell,
    [bool]$DoGeneralize
)

$ErrorActionPreference = "Stop"

# Polls DNS until outbound connectivity is confirmed or the timeout expires.
# A blind sleep is unreliable: too short on slow VMs, always wasteful on fast ones.
function Wait-NetworkReady {
    param([int]$TimeoutSeconds = 120, [int]$PollSeconds = 5)
    $elapsed = 0
    $Host.UI.RawUI.WindowTitle = "Waiting for network..."
    Write-Host "Waiting for network connectivity (timeout ${TimeoutSeconds}s)..."
    while ($elapsed -lt $TimeoutSeconds) {
        try {
            [void][System.Net.Dns]::GetHostEntry("cloudbase.it")
            Write-Host "Network ready after ${elapsed}s."
            return
        } catch { }
        Start-Sleep -Seconds $PollSeconds
        $elapsed += $PollSeconds
    }
    throw "Network not available after ${TimeoutSeconds}s — aborting."
}

# Wraps Invoke-WebRequest with retry/back-off so transient failures don't abort the build.
function Invoke-WebRequestWithRetry {
    param(
        [string]$Uri,
        [string]$OutFile,
        [int]$MaxAttempts = 3,
        [int]$BackoffSeconds = 15
    )
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Write-Host "Downloading $Uri (attempt $attempt/$MaxAttempts)..."
            Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing
            return
        } catch {
            if ($attempt -eq $MaxAttempts) { throw }
            Write-Warning "Download failed (attempt $attempt): $_  Retrying in ${BackoffSeconds}s..."
            Start-Sleep -Seconds $BackoffSeconds
        }
    }
}

try {
    Wait-NetworkReady

    # --- WinRM ---
    # Run all config steps directly in this session — spawning a child powershell.exe
    # per command adds ~2-3s process-init overhead per call (7 calls = ~15-20s wasted).
    $Host.UI.RawUI.WindowTitle = "Configuring WinRM..."
    Start-Service WinRM
    Set-Item WSMan:\localhost\Service\AllowUnencrypted $true -Force
    Set-Item WSMan:\localhost\Service\Auth\Basic $true -Force
    if (-not (Get-NetFirewallRule -DisplayName 'WinRM HTTP' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName 'WinRM HTTP' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5985
    }
    Set-Item WSMan:\localhost\Client\TrustedHosts '*' -Force
    net user Administrator Passw0rd /active:yes
    net localgroup 'Remote Management Users' Administrator /add
    Restart-Service WinRM

    # --- Extra driver injection ---
    if (Test-Path -Path "E:\infs") {
        $Host.UI.RawUI.WindowTitle = "Injecting Windows drivers..."
        # pnputil is built into Windows 8+ — no WDK download/install/uninstall needed.
        Write-Host "Running pnputil to inject drivers from E:\infs..."
        $pnpOutput = & pnputil /add-driver "E:\infs\*.inf" /subdirs /install 2>&1
        Write-Host $pnpOutput
        if ($LASTEXITCODE -ne 0) {
            throw "pnputil driver injection failed (exit $LASTEXITCODE)."
        }
    }

    # --- Cloudbase-Init ---
    $Host.UI.RawUI.WindowTitle = "Installing Cloudbase-Init..."
    Invoke-WebRequestWithRetry -Uri "https://cloudbase.it/downloads/CloudbaseInitSetup_Stable_x64.msi" -OutFile "c:\cloudbase.msi"
    $cloudbaseInitLog = "$ENV:Temp\cloudbase_init.log"
    $serialPorts = @(Get-WmiObject Win32_SerialPort)
    $serialPortName = if ($serialPorts.Count -gt 0) { $serialPorts[0].DeviceId } else { "COM1" }
    $p = Start-Process -Wait -PassThru -FilePath msiexec `
        -ArgumentList "/i c:\cloudbase.msi /qn /norestart /l*v `"$cloudbaseInitLog`" LOGGINGSERIALPORTNAME=$serialPortName"
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) {
        throw "Cloudbase-Init install failed (exit $($p.ExitCode)). Log: $cloudbaseInitLog"
    }

    # --- Virtio drivers ---
    $Host.UI.RawUI.WindowTitle = "Installing Virtio Drivers..."
    certutil -addstore "TrustedPublisher" A:\rh.cer
    Invoke-WebRequestWithRetry `
        -Uri "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win-gt-x64.msi" `
        -OutFile "c:\virtio.msi"
    Invoke-WebRequestWithRetry `
        -Uri "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win-guest-tools.exe" `
        -OutFile "c:\virtio.exe"
    $virtioLog = "$ENV:Temp\virtio.log"
    # /i = regular install (original used /a = administrative/unpack-only, which does not install drivers)
    $p = Start-Process -Wait -PassThru -FilePath msiexec `
        -ArgumentList "/i c:\virtio.msi /qn /norestart /l*v `"$virtioLog`""
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) {
        throw "Virtio MSI install failed (exit $($p.ExitCode)). Log: $virtioLog"
    }
    $p = Start-Process -Wait -PassThru -FilePath "c:\virtio.exe" -ArgumentList "/silent"
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) {
        throw "Virtio guest tools install failed (exit $($p.ExitCode))."
    }

    # Remove the run-once logon script key and auto-logon counter.
    # SilentlyContinue guards against the properties already being absent on a re-run.
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" `
        -Name "Unattend*" -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" `
        -Name "AutoLogonCount" -ErrorAction SilentlyContinue

    $Host.UI.RawUI.WindowTitle = "Running SetSetupComplete..."
    & "$ENV:ProgramFiles\Cloudbase Solutions\Cloudbase-Init\bin\SetSetupComplete.cmd"

    # Debug hook — only reachable when explicitly invoked with -RunPowershell.
    # Never triggered from Autounattend.xml (positional arg 1 binds to $DoGeneralize, not this switch).
    if ($RunPowershell) {
        $Host.UI.RawUI.WindowTitle = "DEBUG: waiting for user to close shell"
        Write-Host "Spawning interactive shell for manual work. Close it to continue the build."
        Start-Process -Wait -PassThru -FilePath powershell | Out-Null
    }

    # Clean up downloaded installers
    Remove-Item -Path "c:\cloudbase.msi" -Force
    Remove-Item -Path "c:\virtio.msi"    -Force
    Remove-Item -Path "c:\virtio.exe"    -Force

    # Marker consumed by post-build verification steps
    New-Item -Path "c:\success.tch" -ItemType File -Force | Out-Null

    $Host.UI.RawUI.WindowTitle = "Running Sysprep..."
    $unattendedXmlPath = "$ENV:ProgramFiles\Cloudbase Solutions\Cloudbase-Init\conf\Unattend.xml"
    if ($DoGeneralize) {
        & "$ENV:SystemRoot\System32\Sysprep\Sysprep.exe" /generalize /oobe /shutdown /unattend:"$unattendedXmlPath"
    } else {
        & "$ENV:SystemRoot\System32\Sysprep\Sysprep.exe" /oobe /shutdown /unattend:"$unattendedXmlPath"
    }
}
catch {
    # Write to both the error log file and the console so the failure appears in the
    # serial/stdio output that Packer captures (communicator = "none" means this is
    # the only signal visible outside the VM).
    $msg = "LOGON SCRIPT FAILED: $_"
    $msg | Out-File "c:\error_log.txt" -Force
    Write-Error $msg
}
