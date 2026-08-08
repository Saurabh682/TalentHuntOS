# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\VibeCode\\JobSearch_Platform\\TalentHuntOS\\app\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\Kumar\\AppData\\Roaming\\Python\\Python313\\site-packages\\nicegui', 'nicegui'), ('D:\\VibeCode\\JobSearch_Platform\\TalentHuntOS\\app', 'app')],
    hiddenimports=['nicegui', 'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'fastapi', 'starlette', 'starlette.responses', 'starlette.routing', 'starlette.staticfiles', 'engineio', 'socketio', 'websockets', 'jinja2', 'sqlalchemy', 'sqlalchemy.ext.asyncio', 'sqlite3', 'alembic', 'app', 'app.main', 'app.config', 'app.config.settings', 'app.config.constants', 'app.ui', 'app.ui.pages', 'app.ui.panels', 'app.ai', 'app.ai.engine', 'app.ai.local_server', 'app.ai.providers', 'app.candidates', 'app.candidates.models', 'app.candidates.search', 'app.candidates.rag', 'app.candidates.service', 'app.hunts', 'app.analytics', 'app.analytics.service', 'app.analytics.reports', 'app.communications', 'app.communications.service', 'app.communications.email_service', 'app.communications.outreach_service', 'app.copilot', 'app.voice', 'app.voice.audio_bridge', 'app.agents', 'app.actions', 'app.infrastructure', 'app.intelligence', 'pydantic', 'pydantic_settings', 'keyring', 'cryptography'],
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
    name='TalentHuntOS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
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
    name='TalentHuntOS',
)
