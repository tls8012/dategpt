from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _reexec_in_repo_venv() -> None:
    if getattr(sys, "frozen", False):
        return

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



from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from backend_client import BackendClient
from main_window import MainWindow
from platform_focus import activate_application


def _resource_path(*parts: str) -> Path:
    candidates = []
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        candidates.append(
            Path(bundle_root).resolve()
        )

    if (
        getattr(sys, "frozen", False)
        and sys.platform == "darwin"
    ):
        executable = Path(sys.executable).resolve()
        candidates.append(
            executable.parent.parent / "Resources"
        )

    candidates.append(
        Path(__file__).resolve().parent.parent
    )

    for root in candidates:
        candidate = root.joinpath(*parts)
        if candidate.exists():
            return candidate
    return candidates[0].joinpath(*parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DateGPT PySide6 desktop frontend"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = QApplication(sys.argv)
    app.setApplicationName("DateGPT")

    style_path = _resource_path(
        "desktop",
        "style.qss",
    )
    if style_path.exists():
        app.setStyleSheet(
            style_path.read_text(encoding="utf-8")
        )

    client = BackendClient(
        worker_script_path=(
            Path(__file__).resolve().parent.parent
            / "BACKEND"
            / "backend.py"
        ),
    )
    window = MainWindow(client)
    app.aboutToQuit.connect(client.shutdown)
    client.running_changed.connect(
        lambda running: (
            activate_application(window)
            if running
            else None
        )
    )

    window.show()
    activate_application(window)
    QTimer.singleShot(
        100,
        client.start,
    )
    QTimer.singleShot(
        250,
        lambda: activate_application(window),
    )
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
