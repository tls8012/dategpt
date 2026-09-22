from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QStackedLayout

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

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        background = base / "background.png"
        character = base / "character.png"

        QImage(64, 36, QImage.Format.Format_RGB32).save(
            str(background)
        )
        QImage(
            24,
            48,
            QImage.Format.Format_ARGB32,
        ).save(str(character))

        window.game.set_segments([
            {
                "kind": "narration",
                "speaker": "",
                "text": "visual smoke",
                "assets": ["B001", "A001"],
                "resolved_assets": [
                    {
                        "id": "B001",
                        "kind": "background",
                        "local_path": str(background),
                    },
                    {
                        "id": "A001",
                        "kind": "character",
                        "local_path": str(character),
                    },
                ],
            },
        ])

        background_pixmap = (
            window.game.background_label.pixmap()
        )
        character_pixmap = (
            window.game.character_labels[0].pixmap()
        )
        if (
            background_pixmap is None
            or background_pixmap.isNull()
            or character_pixmap is None
            or character_pixmap.isNull()
        ):
            print(
                "visual layer smoke test failed",
                file=sys.stderr,
            )
            return 1

        visual_stack = window.game.visual_area.layout()
        if (
            not isinstance(
                visual_stack,
                QStackedLayout,
            )
            or visual_stack.currentWidget()
            is not window.game.character_layer
        ):
            print(
                "character layer is not above background",
                file=sys.stderr,
            )
            return 1

        window.game.set_segments([
            {
                "kind": "narration",
                "speaker": "",
                "text": "background persists",
                "assets": [],
                "resolved_assets": [],
            },
        ])
        persisted = window.game.background_label.pixmap()
        persisted_character = (
            window.game.character_labels[0].pixmap()
        )
        if persisted is None or persisted.isNull():
            print(
                "background did not persist",
                file=sys.stderr,
            )
            return 1
        if (
            persisted_character is None
            or persisted_character.isNull()
        ):
            print(
                "character SCG did not persist",
                file=sys.stderr,
            )
            return 1

        window.game.set_segments([
            {
                "kind": "narration",
                "speaker": "",
                "text": "characters leave",
                "assets": [],
                "resolved_assets": [],
                "clear_characters": True,
            },
        ])
        if any(
            label.pixmap() is not None
            and not label.pixmap().isNull()
            for label in window.game.character_labels
        ):
            print(
                "clear_characters did not clear SCGs",
                file=sys.stderr,
            )
            return 1
        if (
            window.game.background_label.pixmap()
            is None
            or window.game.background_label.pixmap().isNull()
        ):
            print(
                "clearing characters also cleared background",
                file=sys.stderr,
            )
            return 1

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
