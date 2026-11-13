# Stage B transport/host discovery ONLY. No task/service/config/file mutations.
# Uses existing Windows authentication; no credentials read or trust/network changes.
$ErrorActionPreference = 'Stop'
$result = [ordered]@{
    task = 'CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001'
    stage = 'B / Gate 1 access preflight'
    sampled_utc = [DateTime]::UtcNow.ToString('o')
    home_host = $env:COMPUTERNAME
    expected_server = 'DESKTOP-KT4G5SM'
    remote_writes = $false
    credentials_supplied = $false
    network_or_trust_changes = $false
}
if ($env:COMPUTERNAME -ne 'DESKTOP-SC96D3U') { throw 'Unexpected home host' }
$publicRoot = '\\192.168.0.77\Server\Ultra_LLM\Manager_Live'
try {
    $item = Get-Item -LiteralPath $publicRoot
    $result.smb_public = @{ accessible = [bool]$item.PSIsContainer; path = $publicRoot }
} catch {
    $result.smb_public = @{ accessible = $false; error_type = $_.Exception.GetType().FullName; error = $_.Exception.Message }
}
try {
    $opts = New-PSSessionOption -OpenTimeout 6000 -OperationTimeout 6000
    $hostInfo = Invoke-Command -ComputerName 'DESKTOP-KT4G5SM' -Authentication Negotiate -SessionOption $opts -ScriptBlock {
        [pscustomobject]@{ hostname = $env:COMPUTERNAME; os = [Environment]::OSVersion.VersionString; identity_sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value }
    }
    if ($hostInfo.hostname -ne 'DESKTOP-KT4G5SM') { throw 'Remote host identity mismatch' }
    $result.winrm = @{ status = 'PASS'; host = $hostInfo.hostname; os = $hostInfo.os; identity_sid = $hostInfo.identity_sid }
} catch {
    $result.winrm = @{ status = 'UNAVAILABLE'; error_type = $_.Exception.GetType().FullName; error_id = $_.FullyQualifiedErrorId; error = $_.Exception.Message }
}
$cimSession = $null
try {
    $options = New-CimSessionOption -Protocol Dcom
    $cimSession = New-CimSession -ComputerName '192.168.0.77' -SessionOption $options -OperationTimeoutSec 6
    $system = Get-CimInstance -CimSession $cimSession -ClassName Win32_ComputerSystem -OperationTimeoutSec 6
    if ($system.Name -ne 'DESKTOP-KT4G5SM') { throw 'CIM host identity mismatch' }
    $result.cim_dcom = @{ status = 'PASS'; host = $system.Name }
} catch {
    $result.cim_dcom = @{ status = 'UNAVAILABLE'; error_type = $_.Exception.GetType().FullName; error_id = $_.FullyQualifiedErrorId; error = $_.Exception.Message }
} finally {
    if ($cimSession) { Remove-CimSession -CimSession $cimSession }
}
$result | ConvertTo-Json -Depth 6 -Compress
