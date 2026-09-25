"""PyInstaller 진입점 겸 `python run.py` 용 런처.

코드 업데이트로 받은 `dccon` 이 있으면 dccon_boot 가 먼저 올린다.
그 코드가 import 부터 실패하면 버리고 exe 에 든 코드로 뜬다.
"""

import dccon_boot

dccon_boot.activate()
try:
    from dccon.app import main
except Exception:
    if dccon_boot.active is None:
        raise
    dccon_boot.fall_back()
    from dccon.app import main

if __name__ == "__main__":
    raise SystemExit(main())
