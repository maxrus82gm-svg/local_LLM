# Portable Windows x64 Ultra LLM Web Client build.
# Developer-only tool. The release contains the Python runtime and no credentials.
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$BuilderPython,
 [Parameter(Mandatory=$true)][string]$OutputRoot,
 [string]$ReleaseName='UltraLLM_Client_WEB02_Win64'
)
$ErrorActionPreference='Stop'
if($ReleaseName -notmatch '^[A-Za-z0-9_-]{6,80}$'){throw 'Invalid release name'}
$root=[IO.Path]::GetFullPath($OutputRoot)
$src=$PSScriptRoot
if($root.StartsWith($src,[StringComparison]::OrdinalIgnoreCase) -or
   $src.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)){
 throw 'Destination and source must be separate directories'
}
if(-not(Test-Path -LiteralPath $BuilderPython -PathType Leaf)){throw 'BuilderPython not found'}
$version=& $BuilderPython -m PyInstaller --version
if($LASTEXITCODE -ne 0 -or $version -ne '6.16.0'){
 throw 'Builder requires the pinned PyInstaller 6.16.0'
}
$pythonVersion=& $BuilderPython -c 'import sys;print(sys.version_info.major,sys.version_info.minor,sep=chr(46))'
if($LASTEXITCODE -ne 0 -or $pythonVersion -ne '3.12'){
 throw 'Builder requires Python 3.12'
}
$bits=& $BuilderPython -c 'import struct;print(struct.calcsize(chr(80))*8)'
if($LASTEXITCODE -ne 0 -or [string]$bits -ne '64'){
 throw 'Builder requires 64-bit Python'
}
Write-Output ('PACKAGING_TOOLCHAIN=Python '+$pythonVersion+' Win64 / PyInstaller '+$version)
if(-not(Test-Path $root)){New-Item -ItemType Directory -Path $root -Force | Out-Null}
$release=Join-Path $root $ReleaseName
$zip=Join-Path $root ($ReleaseName+'.zip')
$work=Join-Path $root ('_work_'+$ReleaseName)
if((Test-Path $release) -or (Test-Path $zip) -or (Test-Path $work)){
 throw 'Release or build folder already exists; refuse overwrite'
}
$distTemp=Join-Path $work 'dist'
$workTemp=Join-Path $work 'build'
$specTemp=Join-Path $work 'spec'
New-Item -ItemType Directory -Path $work,$distTemp,$workTemp,$specTemp -Force | Out-Null
try {
 $args=@(
   '-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
   '--name','UltraLLMClient',
   '--distpath',$distTemp,'--workpath',$workTemp,'--specpath',$specTemp,
   '--add-data',((Join-Path $src 'web_assets')+';web_assets'),
   '--add-data',((Join-Path $src 'Prepare-ClientPrivate.ps1')+';.'),
   (Join-Path $src 'web_client.py')
 )
 & $BuilderPython @args
 if($LASTEXITCODE -ne 0){throw 'PyInstaller build failed'}
 $built=Join-Path $distTemp 'UltraLLMClient'
 if(-not(Test-Path (Join-Path $built 'UltraLLMClient.exe'))){throw 'EXE not created'}
 foreach($name in @('web_assets\index.html','web_assets\client.css','web_assets\client.js','Prepare-ClientPrivate.ps1')){
   if(-not(Test-Path (Join-Path $built ('_internal\'+$name)))){throw ('Missing asset: '+$name)}
 }
 New-Item -ItemType Directory -Path $release -Force | Out-Null
 Copy-Item -Path (Join-Path $built '*') -Destination $release -Recurse -Force
 foreach($name in @('Start_Ultra_LLM_Client.vbs','Install_Ultra_LLM_Client.vbs','PORTABLE_README.txt')){
   Copy-Item -LiteralPath (Join-Path $src $name) -Destination (Join-Path $release $name)
 }
 $pythonBase=& $BuilderPython -c 'import sys; print(sys.base_prefix)'
 if($LASTEXITCODE -ne 0 -or -not $pythonBase){throw 'Cannot locate bundled Python license'}
 $pythonLicense=Join-Path ([string]$pythonBase).Trim() 'LICENSE.txt'
 if(-not(Test-Path -LiteralPath $pythonLicense -PathType Leaf)){
   throw 'Python license file missing; refusing redistribution without license'
 }
 Copy-Item -LiteralPath $pythonLicense -Destination (Join-Path $release 'PYTHON_LICENSE.txt')
 $manifest=Join-Path $release 'SHA256SUMS.txt'
 $entries=@(Get-ChildItem -LiteralPath $release -Recurse -File |
   Sort-Object FullName | ForEach-Object {
     $relative=$_.FullName.Substring($release.Length+1).Replace('\','/')
     (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()+'  '+$relative
   })
 [IO.File]::WriteAllLines($manifest,[string[]]$entries,[Text.UTF8Encoding]::new($false))
 Compress-Archive -Path $release -DestinationPath $zip -CompressionLevel Optimal -ErrorAction Stop
 Write-Output 'PORTABLE_BUILD_OK'
 Write-Output ('RELEASE_DIR='+$release)
 Write-Output ('RELEASE_ZIP='+$zip)
 Write-Output ('PACKAGED_FILES='+$entries.Count)
 Write-Output ('PORTABLE_ZIP_BYTES='+(Get-Item $zip).Length)
 Write-Output ('PORTABLE_ZIP_SHA256='+(Get-FileHash $zip -Algorithm SHA256).Hash)
} finally {
 if(Test-Path $work){Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue}
}
