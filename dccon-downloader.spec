# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 스펙.

`--exclude-module` 은 파이썬 모듈만 거르고 Qt DLL 은 그대로 남는다.
이 앱은 QtWidgets/QtGui/QtCore 만 쓰는데 기본 수집에는 Qml, Quick, Pdf,
소프트웨어 OpenGL 폴백까지 딸려와 40MB 가까이 낭비된다. 그래서 수집이
끝난 뒤 바이너리 목록에서 직접 걸러낸다.

빌드 옵션은 환경변수로 받는다 (build.ps1 이 설정):
    DCCON_ONEFILE=1   단일 exe
    DCCON_CONSOLE=1   콘솔 창 표시 (디버깅용)
"""

import os

ONEFILE = os.environ.get("DCCON_ONEFILE") == "1"
CONSOLE = os.environ.get("DCCON_CONSOLE") == "1"

# 파이썬 모듈 단계에서 빼는 것들
EXCLUDED_MODULES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DInput",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth",
    "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtDesigner",
    "PySide6.QtTest", "PySide6.QtSql", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtWebSockets",
    "PySide6.QtWebChannel", "PySide6.QtNfc", "PySide6.QtHelp", "PySide6.QtUiTools",
    "tkinter", "unittest", "pydoc_data", "pdb", "doctest",
]

# 수집된 DLL 중 이름에 이게 들어가면 버린다.
#   opengl32sw : 소프트웨어 OpenGL 폴백 (20MB). QtWidgets 는 래스터 엔진을
#                쓰므로 필요 없다. 혹시 그래픽이 깨지는 환경이 나오면
#                이 항목만 빼고 다시 빌드하면 된다.
DROP_BINARIES = (
    "qt6quick", "qt6qml", "qt6pdf", "qt63d", "qt6charts", "qt6datavisualization",
    "qt6graphs", "qt6multimedia", "qt6bluetooth", "qt6positioning",
    "qt6serialport", "qt6designer", "qt6test", "qt6sql", "qt6remoteobjects",
    "qt6scxml", "qt6sensors", "qt6spatialaudio", "qt6texttospeech",
    "qt6websockets", "qt6webchannel", "qt6nfc", "qt6help", "qt6webengine",
    "qt6labs", "opengl32sw",
)

# 데이터 파일(플러그인 등) 중 버릴 경로 조각.
# imageformats 는 절대 건드리면 안 된다 - GIF/JPEG 썸네일이 안 그려진다.
DROP_DATA_DIRS = (
    "pyside6/qml", "pyside6/translations/qtwebengine",
    "pyside6/resources", "pyside6/plugins/qmltooling",
    "pyside6/plugins/sqldrivers", "pyside6/plugins/multimedia",
    "pyside6/plugins/position", "pyside6/plugins/sensors",
    "pyside6/plugins/texttospeech", "pyside6/plugins/designer",
)


def _keep_binary(entry):
    name = entry[0].replace("\\", "/").lower()
    return not any(token in name for token in DROP_BINARIES)


def _keep_data(entry):
    name = entry[0].replace("\\", "/").lower()
    return not any(token in name for token in DROP_DATA_DIRS)


a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[("dccon/gui/assets", "dccon/gui/assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
    optimize=0,
)

_before = len(a.binaries), len(a.datas)
a.binaries = [e for e in a.binaries if _keep_binary(e)]
a.datas = [e for e in a.datas if _keep_data(e)]
print(
    f"[spec] binaries {_before[0]} -> {len(a.binaries)}, "
    f"datas {_before[1]} -> {len(a.datas)}"
)

pyz = PYZ(a.pure)

_common = dict(
    name="dccon-downloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)

if ONEFILE:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        exclude_binaries=False,
        runtime_tmpdir=None,
        **_common,
    )
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **_common)
    coll = COLLECT(
        exe, a.binaries, a.datas,
        strip=False, upx=False, name="dccon-downloader",
    )
