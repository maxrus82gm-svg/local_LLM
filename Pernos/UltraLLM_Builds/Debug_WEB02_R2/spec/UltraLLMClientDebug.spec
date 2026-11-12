# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['M:\\GitHub\\local_LLM_GPT_docs\\Client_Ultra_LLM\\web_client.py'],
    pathex=[],
    binaries=[],
    datas=[('M:\\GitHub\\local_LLM_GPT_docs\\Client_Ultra_LLM\\web_assets', 'web_assets'), ('M:\\GitHub\\local_LLM_GPT_docs\\Client_Ultra_LLM\\Prepare-ClientPrivate.ps1', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='UltraLLMClientDebug',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='UltraLLMClientDebug',
)
