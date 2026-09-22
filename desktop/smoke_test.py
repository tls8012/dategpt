from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from backend_client import BackendClient
from main_window import MainWindow


def main() -> int:
    desktop_dir = Path(__file__).resolve().parent
    repo_root = desktop_dir.parent

    app = QApplication([])
    client = BackendClient(
        worker_script_path=(
            repo_root / "BACKEND" / "backend.py"
        )
    )
    window = MainWindow(client)

    state = {
        "pong": False,
        "fatal": "",
    }

    def on_running(running: bool) -> None:
        if running:
            client.send({"type": "ping"})

    def on_event(event) -> None:
        if (
            event.get("type") == "reply"
            and "pong" in str(event.get("text", ""))
        ):
            state["pong"] = True
            client.shutdown()
            app.quit()

    def on_fatal(message: str) -> None:
        state["fatal"] = message
        client.shutdown()
        app.quit()

    def on_timeout() -> None:
        state["fatal"] = "desktop smoke test timed out"
        client.shutdown()
        app.quit()

    client.running_changed.connect(on_running)
    client.event_received.connect(on_event)
    client.fatal_error.connect(on_fatal)
    QTimer.singleShot(10000, on_timeout)

    client.start()
    app.exec()
    window.close()

    if state["fatal"]:
        print(state["fatal"], file=sys.stderr)
        return 1
    if not state["pong"]:
        print("backend ping did not complete", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
