from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _reexec_in_repo_venv() -> None:
    desktop_dir = Path(__file__).absolute().parent
    repo_root = desktop_dir.parent
    venv_root = repo_root / ".venv"

    if os.name == "nt":
        venv_python = (
            venv_root / "Scripts" / "python.exe"
        )
    else:
        venv_python = venv_root / "bin" / "python"

    if not venv_python.is_file():
        return

    try:
        current_prefix = Path(sys.prefix).absolute()
    except Exception:
        current_prefix = Path(sys.prefix)

    try:
        target_prefix = venv_root.absolute()
    except Exception:
        target_prefix = venv_root

    if current_prefix == target_prefix:
        return

    if os.environ.get(
        "DATEGPT_VENV_REEXEC",
        "",
    ) == "1":
        return

    env = os.environ.copy()
    env["DATEGPT_VENV_REEXEC"] = "1"
    os.execve(
        str(venv_python),
        [
            str(venv_python),
            str(Path(__file__).absolute()),
            *sys.argv[1:],
        ],
        env,
    )


_reexec_in_repo_venv()

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
