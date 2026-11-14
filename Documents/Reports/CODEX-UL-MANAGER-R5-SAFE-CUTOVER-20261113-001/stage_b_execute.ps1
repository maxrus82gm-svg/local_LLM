# B ONLY. Local driver, existing IP/Negotiate WinRM. No stop/start/task mutation.
# Paths/expected metadata filled by the local launcher, never private credentials.
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$session=$null
$rootCreated=$null
try {
    if($env:COMPUTERNAME -ne 'DESKTOP-SC96D3U'){throw 'Wrong home host'}
    $expectedJson=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__EXPECTED_B64__'))
    $preflight=[scriptblock]::Create([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__PREFLIGHT_B64__')))
    $session=New-PSSession -ComputerName 192.168.0.77 -Authentication Negotiate -SessionOption (New-PSSessionOption -OpenTimeout 6000 -OperationTimeout 45000)
    $freshText=Invoke-Command -Session $session -ScriptBlock $preflight
    $fresh=($freshText -join "`n")|ConvertFrom-Json
    if($fresh.status -ne 'PREFLIGHT_READONLY_PASS'){throw 'Fresh complete preflight did not pass; no server write'}
    $init=Invoke-Command -Session $session -ArgumentList $expectedJson -ScriptBlock {
        param($expectedJson)
        $ErrorActionPreference='Stop'
        if($env:COMPUTERNAME -ne 'DESKTOP-KT4G5SM'){throw 'Wrong server host'}
        $expected=$expectedJson|ConvertFrom-Json
        foreach($role in @('manager','qwen_gateway','qwen_engine','valheim')) {
            $want=$expected.$role
            $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$want.pid)
            if(-not $p -or $p.CreationDate.ToUniversalTime().ToString('o') -ne $want.created_utc -or $p.ExecutablePath -ine $want.exe -or (Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid).Sid -ne $want.owner_sid){throw ('Protected identity changed: '+$role)}
        }
        $task=Get-ScheduledTask -TaskName 'UltraLLM_Manager_LIVE'
        if($task.State -ne 'Running' -or @($task.Actions).Count -ne 1){throw 'Manager task changed'}
        $xml=Export-ScheduledTask -TaskName 'UltraLLM_Manager_LIVE'
        $hash=[Security.Cryptography.SHA256]::Create()
        $xmlHash=([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($xml)))).Replace('-','').ToLowerInvariant()
        if($xmlHash -ne $expected.task.xml_sha256){throw 'Task XML changed'}
        if((Get-FileHash -LiteralPath $expected.task.config_path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.python_audit.metadata.config_sha256){throw 'Protected config changed'}
        $base='C:\ProgramData\UltraLLM'
        $node=Get-Item -LiteralPath $base
        while($node) {
            if($node.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse maintenance ancestor'}
            $node=$node.Parent
        }
        $leaf='Manager_R5_STAGEB_'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'_'+[Guid]::NewGuid().ToString('N').Substring(0,8)
        $destination=Join-Path $base $leaf
        if(Test-Path -LiteralPath $destination){throw 'Maintenance destination already exists'}
        [void][IO.Directory]::CreateDirectory($destination)
        # Only the NEW empty directory is secured; all existing ACLs stay intact.
        $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl=Get-Acl -LiteralPath $destination
        $acl.SetAccessRuleProtection($true,$false)
        foreach($rule in @($acl.Access)){[void]$acl.RemoveAccessRuleSpecific($rule)}
        foreach($id in @($sid.Value,'S-1-5-18','S-1-5-32-544')) {
            $account=New-Object Security.Principal.SecurityIdentifier($id)
            $rule=New-Object Security.AccessControl.FileSystemAccessRule($account,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
            $acl.AddAccessRule($rule)
        }
        $acl.SetOwner($sid)
        Set-Acl -LiteralPath $destination -AclObject $acl
        $checked=Get-Acl -LiteralPath $destination
        $allowed=@($sid.Value,'S-1-5-18','S-1-5-32-544')
        if(-not $checked.AreAccessRulesProtected -or @($checked.Access|Where-Object {$_.AccessControlType -eq 'Allow' -and $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin $allowed}).Count){throw 'New maintenance ACL unsafe; no private copy'}
        [void][IO.Directory]::CreateDirectory((Join-Path $destination 'incoming'))
        [pscustomobject]@{maintenance_root=$destination;new_root_protected=$true;allowed_sids=$allowed;host=$env:COMPUTERNAME}
    }
    $rootCreated=$init.maintenance_root
    [pscustomobject]@{phase='NEW_PROTECTED_ROOT';root=$rootCreated;existing_directories_changed=$false}|ConvertTo-Json -Compress
    $zipDestination=Join-Path $rootCreated 'incoming\release.zip'
    $helperDestination=Join-Path $rootCreated 'incoming\stage_b_prepare_server.py'
    Copy-Item -LiteralPath '__LOCAL_ZIP__' -Destination $zipDestination -ToSession $session
    Copy-Item -LiteralPath '__LOCAL_HELPER__' -Destination $helperDestination -ToSession $session
    $preparedText=Invoke-Command -Session $session -ArgumentList $rootCreated,$expectedJson,'__HELPER_SHA__','__VERIFIER_SHA__' -ScriptBlock {
        param($root,$expectedJson,$helperHash,$verifierHash)
        $ErrorActionPreference='Stop'
        if($env:COMPUTERNAME -ne 'DESKTOP-KT4G5SM'){throw 'Wrong server host'}
        $expected=$expectedJson|ConvertFrom-Json
        $helper=Join-Path $root 'incoming\stage_b_prepare_server.py'
        $zip=Join-Path $root 'incoming\release.zip'
        if((Get-FileHash -LiteralPath $helper -Algorithm SHA256).Hash.ToLowerInvariant() -ne $helperHash){throw 'Public helper transfer mismatch'}
        if((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'ba4ebf65af7a0693cf4dce045eb08254434a4475fd4f79e031424c905d661ce2'){throw 'ZIP transfer mismatch; no rebuild'}
        $xml=Export-ScheduledTask -TaskName 'UltraLLM_Manager_LIVE'
        $params=[ordered]@{maintenance_root=$root;task_xml_utf8_b64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($xml));task_xml_sha256=$expected.task.xml_sha256;config_sha256=$expected.python_audit.metadata.config_sha256;verifier_sha256=$verifierHash;source_top_hashes=[ordered]@{}}
        foreach($row in $expected.public_code){$params.source_top_hashes[$row.name]=$row.sha256}
        $encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($params|ConvertTo-Json -Depth 8 -Compress)))
        if($encoded.Length -gt 20000){throw 'Private metadata argument too large; do not emit it'}
        $output=@(& $expected.task.executable -I -X utf8 -B $helper $encoded $zip)
        $code=$LASTEXITCODE
        if($code -ne 0){throw ('B helper refused preparation; sanitized result: '+($output -join ' '))}
        $output -join "`n"
    }
    $prepared=($preparedText -join "`n")|ConvertFrom-Json
    if($prepared.status -ne 'BACKUP_STAGING_PREPARED'){throw 'B helper did not pass'}
    $aclResult=Invoke-Command -Session $session -ArgumentList $rootCreated,$expectedJson -ScriptBlock {
        param($root,$expectedJson)
        $ErrorActionPreference='Stop'
        if($env:COMPUTERNAME -ne 'DESKTOP-KT4G5SM'){throw 'Wrong host'}
        $expected=$expectedJson|ConvertFrom-Json
        $rootFull=[IO.Path]::GetFullPath($root)
        if(-not $rootFull.StartsWith('C:\ProgramData\UltraLLM\Manager_R5_STAGEB_',[StringComparison]::OrdinalIgnoreCase)){throw 'ACL check escaped maintenance root'}
        # Apply original PRIVATE ACL only to a NEW empty rehearsal directory/file.
        $probe=Join-Path $root 'rollback_acl_probe'
        if(Test-Path -LiteralPath $probe){throw 'ACL probe already exists'}
        [void][IO.Directory]::CreateDirectory($probe)
        $original=Get-Acl -LiteralPath (Split-Path -Parent $expected.task.config_path)
        Set-Acl -LiteralPath $probe -AclObject $original
        $sections=[Security.AccessControl.AccessControlSections]::Access -bor [Security.AccessControl.AccessControlSections]::Owner -bor [Security.AccessControl.AccessControlSections]::Group
        if((Get-Acl -LiteralPath $probe).GetSecurityDescriptorSddlForm($sections) -ne $original.GetSecurityDescriptorSddlForm($sections)){throw 'Private ACL restore rehearsal mismatch'}
        $file=Join-Path $probe 'synthetic_acl_probe.bin'
        [IO.File]::WriteAllBytes($file,[Text.Encoding]::ASCII.GetBytes('SYNTHETIC ACL PROBE'))
        $originalFileAcl=Get-Acl -LiteralPath $expected.task.config_path
        Set-Acl -LiteralPath $file -AclObject $originalFileAcl
        if((Get-Acl -LiteralPath $file).GetSecurityDescriptorSddlForm($sections) -ne $originalFileAcl.GetSecurityDescriptorSddlForm($sections)){throw 'File ACL restore rehearsal mismatch'}
        $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        $allowed=@($sid,'S-1-5-18','S-1-5-32-544')
        $items=@(Get-Item -LiteralPath $root -Force)+@(Get-ChildItem -LiteralPath $root -Recurse -Force)
        foreach($p in $items) {
            if($p.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Reparse point in new maintenance tree'}
            $a=Get-Acl -LiteralPath $p.FullName
            if(@($a.Access|Where-Object {$_.AccessControlType -eq 'Allow' -and $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin $allowed}).Count){throw 'Broad grant in new protected backup/staging tree'}
        }
        [pscustomobject]@{new_tree_items_checked=$items.Count;only_allow_sids=$allowed;private_directory_acl_restore='PASS';private_file_acl_restore='PASS';existing_acl_changes=$false}
    }
    $postText=Invoke-Command -Session $session -ScriptBlock $preflight
    $post=($postText -join "`n")|ConvertFrom-Json
    if($post.status -ne 'PREFLIGHT_READONLY_PASS'){throw 'Post B protective checks failed; retain all new directories'}
    $expected=$expectedJson|ConvertFrom-Json
    foreach($role in @('manager','qwen_gateway','qwen_engine','valheim')) {
        if($post.$role.pid -ne $expected.$role.pid -or $post.$role.created_utc -ne $expected.$role.created_utc -or $post.$role.exe -ine $expected.$role.exe -or $post.$role.owner_sid -ne $expected.$role.owner_sid){throw ('Post B protected identity changed: '+$role)}
    }
    if($post.task.xml_sha256 -ne $expected.task.xml_sha256 -or $post.python_audit.metadata.config_sha256 -ne $expected.python_audit.metadata.config_sha256 -or $post.python_audit.metadata.tls_peer_sha256 -ne $expected.python_audit.metadata.tls_peer_sha256){throw 'Task/config/TLS changed across B'}
    [ordered]@{status='B PASS / GATE 2 / OWNER GO C REQUIRED';backup_staging=$prepared;backup_acl=$aclResult;post=$post;protected_processes_task_config_tls_unchanged=$true;stage_c_d='NOT RUN';maintenance_root=$rootCreated}|ConvertTo-Json -Depth 15 -Compress
} catch {
    [ordered]@{status='B BLOCKED';maintenance_root=$rootCreated;error_type=$_.Exception.GetType().FullName;error=$_.Exception.Message;partial_directories_retained=$true;stage_c_d='NOT RUN';working_directories_switched=$false}|ConvertTo-Json -Depth 5 -Compress
    exit 2
} finally {
    if($session){Remove-PSSession -Session $session}
}
