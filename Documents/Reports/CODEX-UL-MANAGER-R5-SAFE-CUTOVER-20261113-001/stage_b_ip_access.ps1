# Read-only access correction: IP already listed in TrustedHosts, existing auth.
# No Set-Item/credentials retrieval/config changes/task/process/file mutations.
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'DESKTOP-SC96D3U') { throw 'Unexpected home host' }
$result = [ordered]@{
    task = 'CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001'
    sampled_utc = [DateTime]::UtcNow.ToString('o')
    home_host = $env:COMPUTERNAME
    target_ip = '192.168.0.77'
    settings_changed = $false
    credentials_supplied_or_retrieved = $false
}
try {
    $result.trusted_hosts = [string](Get-Item -LiteralPath 'WSMan:\localhost\Client\TrustedHosts').Value
} catch {
    $result.trusted_hosts_error = @{ type = $_.Exception.GetType().FullName; id = $_.FullyQualifiedErrorId; message = $_.Exception.Message }
}
try {
    $probe = Test-WSMan -ComputerName '192.168.0.77'
    $result.wsman = @{ status = 'REACHABLE'; protocol_version = [string]$probe.ProtocolVersion; vendor = [string]$probe.ProductVendor }
} catch {
    $result.wsman = @{ status = 'UNAVAILABLE'; type = $_.Exception.GetType().FullName; id = $_.FullyQualifiedErrorId; message = $_.Exception.Message }
}
try {
    $options = New-PSSessionOption -OpenTimeout 6000 -OperationTimeout 10000
    $remote = Invoke-Command -ComputerName '192.168.0.77' -Authentication Negotiate -SessionOption $options -ScriptBlock {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        [pscustomobject]@{
            hostname = $env:COMPUTERNAME
            machine_name = [Environment]::MachineName
            execution_pid = $PID
            identity_name = $id.Name
            identity_sid = $id.User.Value
            authentication_type = $id.AuthenticationType
            is_system = $id.IsSystem
            powershell_version = $PSVersionTable.PSVersion.ToString()
            server_local_manager_path_exists = [IO.Directory]::Exists('C:\Server\Ultra_LLM\Manager_Live')
        }
    }
    if ($remote.hostname -ne 'DESKTOP-KT4G5SM' -or $remote.machine_name -ne 'DESKTOP-KT4G5SM') {
        throw 'Remote host identity mismatch'
    }
    $result.invoke_ip = @{ status = 'PASS'; context = $remote | Select-Object hostname,machine_name,execution_pid,identity_name,identity_sid,authentication_type,is_system,powershell_version,server_local_manager_path_exists }
} catch {
    $result.invoke_ip = @{ status = 'UNAVAILABLE'; type = $_.Exception.GetType().FullName; id = $_.FullyQualifiedErrorId; message = $_.Exception.Message }
}
$result | ConvertTo-Json -Depth 6 -Compress
