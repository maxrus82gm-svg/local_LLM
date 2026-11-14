# Independent reviewer template: read-only, not executed by author after B.
$ErrorActionPreference='Stop'
Invoke-Command -ComputerName 192.168.0.77 -Authentication Negotiate -ScriptBlock {
    $ErrorActionPreference='Stop'
    if($env:COMPUTERNAME -ne 'DESKTOP-KT4G5SM'){throw 'Wrong server'}
    $root='C:\ProgramData\UltraLLM\Manager_R5_STAGEB_20261114T063715Z_685df77d'
    $helper=Join-Path $root 'incoming\stage_b_prepare_server.py'
    if((Get-FileHash -LiteralPath $helper -Algorithm SHA256).Hash.ToLowerInvariant() -ne '4c771dddf75e70209c5a15095e4eab4996c4a41122d645e0b570f2a2f5aedf3b'){throw 'Helper changed'}
    $python='C:\Users\silver\AppData\Local\Programs\Python\Python312\python.exe'
    $code=@'
import hashlib,importlib.util,json,pathlib,ssl,sys,zipfile
root=pathlib.Path(sys.argv[1]);file=root/'incoming/stage_b_prepare_server.py'
spec=importlib.util.spec_from_file_location('backup_readonly',file);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
manifest=json.loads((root/'backups/backup_manifest_PRIVATE.json').read_text(encoding='utf-8'))
helper.verify_snapshot(root/'backups/code',manifest['code']);helper.verify_snapshot(root/'backups/state',manifest['state'])
package=root/'package/UltraLLM_Manager_R5_compat_Win64.zip';assert hashlib.sha256(package.read_bytes()).hexdigest()=='ba4ebf65af7a0693cf4dce045eb08254434a4475fd4f79e031424c905d661ce2'
verifier=root/'staging/manager_release.py'
with zipfile.ZipFile(package) as archive:assert verifier.read_bytes()==archive.read('manager_release.py')
spec=importlib.util.spec_from_file_location('release_readonly',verifier);release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
release.read_package(root/'staging')
config=root/'backups/state/private/manager.json';cfg=json.loads(config.read_text(encoding='utf-8-sig'))
ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(root/'backups/state/private'/pathlib.Path(cfg['cert_file']).name,root/'backups/state/private'/pathlib.Path(cfg['key_file']).name)
assert hashlib.sha256((root/'backups/task_original.xml').read_bytes().decode('utf-16').encode('utf-8')).hexdigest()==manifest['task_xml_canonical_utf8_sha256']
print(json.dumps({'backup_bytes':'PASS','backup_tls_pair':'PASS','task_xml':'PASS','staging_21_files':'PASS','private_data_exported':False,'mutations':False}))
'@
    $encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($code))
    & $python -I -B -c 'import base64,sys;exec(base64.b64decode(sys.argv.pop(1)))' $encoded $root
    if($LASTEXITCODE -ne 0){throw 'Read-only verification failed'}
}
