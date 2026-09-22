from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
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
    window.resize(1200, 800)
    window.show()
    app.processEvents()

    crop_source = QImage(
        20,
        100,
        QImage.Format.Format_ARGB32,
    )
    crop_source.fill(0)
    for y in range(10, 90):
        for x in range(5, 15):
            crop_source.setPixelColor(
                x,
                y,
                QColor(255, 255, 255, 255),
            )

    cropped = window.game._upper_body_pixmap(
        QPixmap.fromImage(crop_source)
    )
    if not (
        50 <= cropped.height() <= 56
    ):
        print(
            "upper-body SCG crop has unexpected height",
            file=sys.stderr,
        )
        return 1

    # A cartridge with no backgrounds is still valid.
    window.game.set_session({
        "game_name": "no-background",
        "game_id": "smoke",
        "needs_setup": False,
        "fallback_background": None,
    })
    if (
        window.game.background_label.pixmap()
        is not None
        and not window.game.background_label.pixmap().isNull()
    ):
        print(
            "background unexpectedly exists",
            file=sys.stderr,
        )
        return 1

    window.game.set_segments([
        {
            "kind": "narration",
            "speaker": "",
            "text": "text-only scene",
            "assets": [],
            "resolved_assets": [],
        },
    ])
    if window.game.dialogue_text.text() != "text-only scene":
        print(
            "text-only scene did not render",
            file=sys.stderr,
        )
        return 1
    if any(
        label.pixmap() is not None
        and not label.pixmap().isNull()
        for label in window.game.character_labels
    ):
        print(
            "SCG unexpectedly exists in zero-asset scene",
            file=sys.stderr,
        )
        return 1
    if any(
        asset is not None
        for asset in window.game._character_label_assets
    ):
        print(
            "character visual state unexpectedly exists",
            file=sys.stderr,
        )
        return 1

    stage_height_before_input = (
        window.game.visual_area.height()
    )
    dialogue_rect = window.game.dialogue.geometry()
    window.game.show_input()
    app.processEvents()
    if (
        window.game.visual_area.height()
        != stage_height_before_input
    ):
        print(
            "input panel changed visual stage height",
            file=sys.stderr,
        )
        return 1
    if (
        window.game.input_frame.geometry()
        != dialogue_rect
    ):
        print(
            "input and dialogue panels differ in size",
            file=sys.stderr,
        )
        return 1
    window.game.hide_input()
    app.processEvents()

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        background = base / "background.png"
        character = base / "character.png"
        character_two = base / "character_two.png"

        QImage(64, 36, QImage.Format.Format_RGB32).save(
            str(background)
        )
        QImage(
            24,
            48,
            QImage.Format.Format_ARGB32,
        ).save(str(character))
        QImage(
            24,
            48,
            QImage.Format.Format_ARGB32,
        ).save(str(character_two))

        window.game.set_session({
            "game_name": "smoke",
            "game_id": "fallback",
            "needs_setup": False,
            "fallback_background": {
                "id": "B001",
                "kind": "background",
                "local_path": str(background),
            },
        })
        window.game.set_segments([
            {
                "kind": "narration",
                "speaker": "",
                "text": "fallback background",
                "assets": [],
                "resolved_assets": [],
            },
        ])
        app.processEvents()
        fallback_pixmap = (
            window.game.background_label.pixmap()
        )
        if (
            fallback_pixmap is None
            or fallback_pixmap.isNull()
        ):
            print(
                "fallback background did not render",
                file=sys.stderr,
            )
            return 1

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

        app.processEvents()
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

        visual_width = max(
            1,
            window.game.visual_area.width(),
        )
        visual_height = max(
            1,
            window.game.visual_area.height(),
        )
        if (
            background_pixmap.width()
            < visual_width
            or background_pixmap.height()
            < visual_height
        ):
            print(
                "background pixmap is stale after stage resize",
                file=sys.stderr,
            )
            return 1

        overlay_width = max(
            1,
            window.game.overlay_layer.width(),
        )
        expected_panel_width = max(
            1,
            overlay_width
            - window.game._panel_margin * 2,
        )
        if abs(
            window.game.dialogue.width()
            - expected_panel_width
        ) > 2:
            print(
                "dialogue overlay kept stale width",
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
            is not window.game.overlay_layer
            or not (
                visual_stack.indexOf(
                    window.game.background_label
                )
                < visual_stack.indexOf(
                    window.game.character_layer
                )
                < visual_stack.indexOf(
                    window.game.overlay_layer
                )
            )
        ):
            print(
                "VN visual/overlay layer order is invalid",
                file=sys.stderr,
            )
            return 1

        # One character is centered automatically.
        window.game._layout_character_labels(
            animate=False
        )
        first_rect = (
            window.game.character_labels[0].geometry()
        )
        layer_center = (
            window.game.character_layer.width() // 2
        )
        if abs(
            first_rect.center().x()
            - layer_center
        ) > 2:
            print(
                "single SCG is not centered",
                file=sys.stderr,
            )
            return 1

        # Two characters become left/right slots. The existing
        # character should have a move animation available.
        window.game._render_assets(
            [
                {
                    "id": "A001",
                    "kind": "character",
                    "local_path": str(character),
                    "metadata": {
                        "character": "One",
                    },
                },
                {
                    "id": "A002",
                    "kind": "character",
                    "local_path": str(character_two),
                    "metadata": {
                        "character": "Two",
                    },
                },
            ],
            animate=True,
        )
        if not window.game._active_animations:
            print(
                "SCG transition animation was not created",
                file=sys.stderr,
            )
            return 1
        window.game._layout_character_labels(
            animate=False
        )
        visible_rects = [
            label.geometry()
            for index, label in enumerate(
                window.game.character_labels
            )
            if window.game._character_label_assets[
                index
            ] is not None
        ]
        if (
            len(visible_rects) != 2
            or not (
                visible_rects[0].center().x()
                < layer_center
                < visible_rects[1].center().x()
            )
        ):
            print(
                "two SCGs are not in left/right slots",
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
