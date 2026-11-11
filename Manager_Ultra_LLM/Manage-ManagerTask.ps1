# Portable LAN-only read-only Manager deployment via Windows Task Scheduler.
# No Colibri model START/STOP. No WAN, credentials, or hardcoded machine IPs.
[CmdletBinding()]
param(
    [ValidateSet('Install','Status','Remove')]
    [string]$Action = 'Status',
    [Parameter(Mandatory=$true)]
    [string]$ConfigPath,
    [string]$PythonExe,
    [string]$TaskUser,
    [string]$TaskName = 'UltraLLM_Manager_LIVE'
)
$ErrorActionPreference = 'Stop'
$cfgPath = [IO.Path]::GetFullPath($ConfigPath)
if (-not (Test-Path -LiteralPath $cfgPath -PathType Leaf)) {
    throw 'Manager config file not found'
}
$cfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
$bind = [string]$cfg.bind_host
$port = [int]$cfg.listen_port
$allowed = @($cfg.allowed_client_ips)
if (-not $bind -or $port -lt 1024 -or $port -gt 65535 -or $allowed.Count -lt 1) {
    throw 'Manager LAN bind/port/allowlist invalid'
}
$ruleName = 'UltraLLM_Manager_LAN_' + $port
$hostFile = Join-Path $PSScriptRoot 'live_manager.py'
$managerDir = Split-Path -Parent (Split-Path -Parent $cfgPath)
$logDir = Join-Path $managerDir 'logs'

function Get-LivePort {
    return @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $port -and $_.LocalAddress -eq $bind })
}
function Show-State {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    Write-Output ('TASK_EXISTS=' + [bool]$task)
    if ($task) {
        Write-Output ('TASK_STATE=' + $task.State)
        Write-Output ('TASK_USER=' + $task.Principal.UserId)
        Write-Output ('TASK_LOGON=' + $task.Principal.LogonType)
        Write-Output ('TASK_TRIGGERS=' + @($task.Triggers).Count)
    }
    Write-Output ('LAN_FIREWALL_EXISTS=' + [bool]$rule)
    if ($rule) {
        $addresses = @(Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule)
        Write-Output ('LAN_REMOTE_ALLOWLIST=' + (($addresses | Select-Object -ExpandProperty RemoteAddress) -join ','))
    }
    $listener = @(Get-LivePort)
    Write-Output ('LAN_LISTENER_COUNT=' + $listener.Count)
    if ($listener.Count -eq 1) {
        Write-Output ('LAN_LISTENER_PID=' + $listener[0].OwningProcess)
    }
}

if ($Action -eq 'Status') {
    Show-State
    return
}
$admin = [Security.Principal.WindowsPrincipal]([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $admin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator elevation required for task/firewall management'
}
if ($Action -eq 'Remove') {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    }
    if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
        Remove-NetFirewallRule -Name $ruleName -ErrorAction Stop
    }
    Start-Sleep -Milliseconds 700
    Show-State
    return
}
if (-not $PythonExe -or -not $TaskUser) {
    throw 'Install requires -PythonExe and -TaskUser'
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw 'Python exe absent' }
if (-not (Test-Path -LiteralPath $hostFile -PathType Leaf)) { throw 'Manager code absent' }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw 'Task already exists: refusing replacement'
}
if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
    throw 'Firewall rule already exists: refusing replacement'
}
if (@(Get-LivePort).Count -ne 0) {
    throw 'Configured TCP listener already exists: refusing takeover'
}
if (@(Get-NetIPAddress -IPAddress $bind -ErrorAction SilentlyContinue).Count -eq 0) {
    throw 'Configured local bind IP is not assigned to this machine'
}
& $PythonExe -B $hostFile --config $cfgPath --check-config
if ($LASTEXITCODE -ne 0) { throw 'Python Manager validation failed' }

$createdRule = $false
$createdTask = $false
try {
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Path $logDir -ErrorAction Stop | Out-Null
        $sid = ([Security.Principal.NTAccount]$TaskUser).Translate(
                [Security.Principal.SecurityIdentifier]).Value
        & icacls.exe $logDir '/inheritance:r' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Log ACL inheritance setup failed' }
        & icacls.exe $logDir '/grant:r' ('*' + $sid + ':(OI)(CI)M') '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Log private ACL setup failed' }
    }
    if (-not (Get-Acl -LiteralPath $logDir).AreAccessRulesProtected) {
        throw 'Existing log directory has inherited permissions'
    }
    $arguments = '-u -B "' + $hostFile + '" --config "' + $cfgPath + '" --log-dir "' + $logDir + '"'
    $actionObject = New-ScheduledTaskAction -Execute $PythonExe -Argument $arguments -WorkingDirectory $PSScriptRoot
    $principal = New-ScheduledTaskPrincipal -UserId $TaskUser -LogonType S4U -RunLevel Limited
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
    $taskObject = New-ScheduledTask -Action $actionObject -Principal $principal -Trigger $trigger -Settings $settings
    Register-ScheduledTask -TaskName $TaskName -InputObject $taskObject -ErrorAction Stop | Out-Null
    $createdTask = $true
    $firewallParams = @{
        Name=$ruleName
        DisplayName=$ruleName
        Enabled='True'
        Direction='Inbound'
        Action='Allow'
        Protocol='TCP'
        LocalAddress=$bind
        LocalPort=$port
        RemoteAddress=$allowed
        Program=$PythonExe
        Profile='Any'
    }
    New-NetFirewallRule @firewallParams -ErrorAction Stop | Out-Null
    $createdRule = $true
    Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $until = (Get-Date).AddSeconds(18)
    do {
        Start-Sleep -Milliseconds 400
        $found = @(Get-LivePort)
        if ($found.Count -gt 0) { break }
    } while ((Get-Date) -lt $until)
    if ($found.Count -ne 1) { throw 'Manager did not bind within startup deadline' }
    $process = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $found[0].OwningProcess)
    if (-not $process -or $process.ExecutablePath -ine $PythonExe -or
            $process.CommandLine -notlike '*live_manager.py*') {
        throw 'Unexpected process owns Manager port'
    }
    Write-Output 'MANAGER_PERSISTENT_DEPLOYED'
    Show-State
} catch {
    Write-Output ('INSTALL_ROLLBACK_CAUSE=' + $_.Exception.GetType().Name)
    if ($createdTask) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    if ($createdRule) {
        Remove-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    }
    # Retain protected logs for diagnosis; secrets and model files untouched.
    throw
}
