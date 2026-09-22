"""PyInstaller 진입점 겸 `python run.py` 용 런처."""

from dccon.app import main

if __name__ == "__main__":
    raise SystemExit(main())
