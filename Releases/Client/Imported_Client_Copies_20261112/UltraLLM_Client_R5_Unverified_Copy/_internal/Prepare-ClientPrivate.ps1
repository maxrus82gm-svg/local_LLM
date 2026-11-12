# Owner-run once, on the computer where Ultra LLM Client will be installed.
# Does not create tokens, connect to a server, or open a network port.
$ErrorActionPreference = 'Stop'
$target = Join-Path $env:LOCALAPPDATA 'UltraLLM\Client'
if (Test-Path -LiteralPath $target) {
    $items = @(Get-ChildItem -LiteralPath $target -Force)
    if ($items.Count -gt 0) {
        throw "Existing private directory has content: review manually; refusing ACL changes"
    }
} else {
    New-Item -ItemType Directory -Path $target -Force -ErrorAction Stop | Out-Null
}
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $target '/inheritance:r' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Failed to remove inherited ACLs' }
& icacls.exe $target '/grant:r' ("*" + $sid + ":(OI)(CI)F") '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Failed to install private ACL' }
$acl = Get-Acl -LiteralPath $target
if (-not $acl.AreAccessRulesProtected) { throw 'ACL inheritance still enabled' }
Write-Output "PRIVATE_CLIENT_DIRECTORY_READY"
Write-Output $target
