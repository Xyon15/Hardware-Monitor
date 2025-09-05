# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['performance_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('monitor_pdp.png', '.'), ('monitor_pdp.ico', '.')],
    hiddenimports=['PySide6.QtNetwork'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PyQt5.QtNetwork', 'PyQt5.sip'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HardwareMonitorUI',
    icon='monitor_pdp.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
