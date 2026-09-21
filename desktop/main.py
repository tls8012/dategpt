from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from backend_client import BackendClient
from main_window import MainWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DateGPT PySide6 desktop frontend"
    )
    parser.add_argument(
        "--backend",
        type=Path,
        default=None,
        help="Path to BACKEND/backend.py",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    desktop_dir = Path(__file__).resolve().parent
    repo_root = desktop_dir.parent
    backend_path = (
        args.backend
        if args.backend is not None
        else repo_root / "BACKEND" / "backend.py"
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DateGPT")

    style_path = desktop_dir / "style.qss"
    if style_path.exists():
        app.setStyleSheet(
            style_path.read_text(encoding="utf-8")
        )

    client = BackendClient(
        backend_path,
    )
    window = MainWindow(client)
    app.aboutToQuit.connect(client.shutdown)

    window.show()
    client.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
