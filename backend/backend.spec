# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for TLI Builder backend.
# Run from project root: pyinstaller backend/backend.spec --distpath backend-dist --workpath backend-build --noconfirm
# Output: backend-dist/backend.exe

a = Analysis(
    ['server.py'],
    pathex=['backend'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='backend',
    console=True,
    onefile=True,
)
