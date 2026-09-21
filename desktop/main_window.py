from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDockWidget,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from backend_client import BackendClient


class LauncherPage(QWidget):
    scenario_changed = Signal(object)
    refresh_requested = Signal()
    install_requested = Signal()
    new_game_requested = Signal(object)
    continue_requested = Signal(object, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(90, 70, 90, 70)
        root.setSpacing(18)

        title = QLabel("DateGPT")
        title.setObjectName("Title")
        root.addWidget(title)

        subtitle = QLabel(
            "설치된 시나리오를 고르고 새 게임을 시작하거나 기존 플레이를 이어갑니다."
        )
        subtitle.setObjectName("Muted")
        root.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(14)

        scenario_row = QHBoxLayout()
        self.scenario_combo = QComboBox()
        self.scenario_combo.setMinimumWidth(420)
        self.refresh_button = QPushButton("새로고침")
        self.install_button = QPushButton("시나리오 설치")
        scenario_row.addWidget(self.scenario_combo, 1)
        scenario_row.addWidget(self.refresh_button)
        scenario_row.addWidget(self.install_button)
        card_layout.addLayout(scenario_row)

        self.instance_label = QLabel("이어할 플레이")
        self.instance_label.setObjectName("Muted")
        card_layout.addWidget(self.instance_label)

        self.instance_combo = QComboBox()
        card_layout.addWidget(self.instance_combo)

        action_row = QHBoxLayout()
        self.new_button = QPushButton("새 게임")
        self.new_button.setObjectName("Primary")
        self.continue_button = QPushButton("이어하기")
        action_row.addWidget(self.new_button)
        action_row.addWidget(self.continue_button)
        card_layout.addLayout(action_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Status")
        self.status_label.setWordWrap(True)
        card_layout.addWidget(self.status_label)

        root.addWidget(card)
        root.addStretch(1)

        self.refresh_button.clicked.connect(
            self.refresh_requested.emit
        )
        self.install_button.clicked.connect(
            self.install_requested.emit
        )
        self.scenario_combo.currentIndexChanged.connect(
            self._emit_scenario_changed
        )
        self.new_button.clicked.connect(
            self._emit_new_game
        )
        self.continue_button.clicked.connect(
            self._emit_continue
        )

        self.set_cartridges([])

    def current_cartridge(self) -> Optional[Dict[str, Any]]:
        data = self.scenario_combo.currentData()
        return dict(data) if isinstance(data, dict) else None

    def set_cartridges(
        self,
        cartridges: Iterable[Dict[str, Any]],
    ) -> None:
        previous = self.current_cartridge() or {}
        previous_key = (
            previous.get("game_name"),
            previous.get("build_version"),
        )

        self.scenario_combo.blockSignals(True)
        self.scenario_combo.clear()

        items = sorted(
            (dict(item) for item in cartridges),
            key=lambda item: (
                str(item.get("game_name", "")),
                str(item.get("build_version", "")),
            ),
        )

        selected_index = -1
        for index, item in enumerate(items):
            game_name = str(item.get("game_name", "(unknown)"))
            build = str(item.get("build_version", "?"))
            self.scenario_combo.addItem(
                "{}  /  build {}".format(game_name, build),
                item,
            )
            if (
                game_name,
                build,
            ) == previous_key:
                selected_index = index

        if selected_index >= 0:
            self.scenario_combo.setCurrentIndex(
                selected_index
            )
        self.scenario_combo.blockSignals(False)

        has_items = self.scenario_combo.count() > 0
        self.new_button.setEnabled(has_items)
        self.continue_button.setEnabled(False)
        self.instance_combo.clear()

        if has_items:
            self._emit_scenario_changed()
            self.set_status("")
        else:
            self.set_status(
                "설치된 시나리오가 없습니다. "
                "'시나리오 설치'에서 로컬 폴더 또는 GitHub 주소를 넣을 수 있습니다."
            )

    def set_game_ids(self, game_ids: Iterable[str]) -> None:
        ids = [str(value) for value in game_ids]
        self.instance_combo.clear()
        for game_id in ids:
            self.instance_combo.addItem(game_id, game_id)
        self.continue_button.setEnabled(bool(ids))
        self.instance_combo.setEnabled(bool(ids))
        if ids:
            self.instance_label.setText(
                "이어할 플레이 ({})".format(len(ids))
            )
        else:
            self.instance_label.setText(
                "이어할 플레이 없음"
            )

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _emit_scenario_changed(self) -> None:
        cartridge = self.current_cartridge()
        self.set_game_ids([])
        if cartridge is not None:
            self.scenario_changed.emit(cartridge)

    def _emit_new_game(self) -> None:
        cartridge = self.current_cartridge()
        if cartridge is not None:
            self.new_game_requested.emit(cartridge)

    def _emit_continue(self) -> None:
        cartridge = self.current_cartridge()
        game_id = self.instance_combo.currentData()
        if cartridge is not None and game_id:
            self.continue_requested.emit(
                cartridge,
                str(game_id),
            )


class GamePage(QWidget):
    send_requested = Signal(str)
    settings_requested = Signal()
    checkpoint_requested = Signal()
    onboarding_mode_requested = Signal(str)
    onboarding_finalize_requested = Signal()
    launcher_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.needs_setup = False

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 22)
        root.setSpacing(12)

        top = QHBoxLayout()
        self.session_label = QLabel("세션 없음")
        self.session_label.setObjectName("Muted")
        top.addWidget(self.session_label)
        top.addStretch(1)

        self.save_button = QPushButton("저장")
        self.settings_button = QPushButton("설정")
        self.launcher_button = QPushButton("시나리오 선택")
        top.addWidget(self.save_button)
        top.addWidget(self.settings_button)
        top.addWidget(self.launcher_button)
        root.addLayout(top)

        self.stage = QFrame()
        self.stage.setObjectName("Stage")
        stage_layout = QVBoxLayout(self.stage)
        stage_layout.addStretch(1)
        stage_hint = QLabel(
            "캐릭터 / 배경 표시 영역\n"
            "(이미지 파이프라인은 다음 단계에서 연결)"
        )
        stage_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stage_hint.setObjectName("Muted")
        stage_layout.addWidget(stage_hint)
        stage_layout.addStretch(1)
        root.addWidget(self.stage, 1)

        dialogue = QFrame()
        dialogue.setObjectName("DialogueCard")
        dialogue_layout = QVBoxLayout(dialogue)
        dialogue_layout.setContentsMargins(20, 14, 20, 14)
        dialogue_layout.setSpacing(7)

        self.speaker_label = QLabel("DateGPT")
        self.speaker_label.setObjectName("Speaker")
        dialogue_layout.addWidget(self.speaker_label)

        self.dialogue_text = QPlainTextEdit()
        self.dialogue_text.setReadOnly(True)
        self.dialogue_text.setMaximumHeight(135)
        dialogue_layout.addWidget(self.dialogue_text)

        root.addWidget(dialogue)

        self.onboarding_frame = QFrame()
        onboarding_layout = QHBoxLayout(
            self.onboarding_frame
        )
        onboarding_layout.setContentsMargins(0, 0, 0, 0)
        self.original_button = QPushButton("새 캐릭터")
        self.existing_button = QPushButton("기존 캐릭터")
        self.observer_button = QPushButton("관전자")
        self.finalize_button = QPushButton("온보딩 완료")
        onboarding_layout.addWidget(self.original_button)
        onboarding_layout.addWidget(self.existing_button)
        onboarding_layout.addWidget(self.observer_button)
        onboarding_layout.addStretch(1)
        onboarding_layout.addWidget(self.finalize_button)
        root.addWidget(self.onboarding_frame)
        self.onboarding_frame.hide()

        input_row = QHBoxLayout()
        self.input_box = QPlainTextEdit()
        self.input_box.setPlaceholderText(
            "하고 싶은 말을 입력하세요.  Ctrl+Enter로 전송"
        )
        self.input_box.setMaximumHeight(92)
        self.send_button = QPushButton("전송")
        self.send_button.setObjectName("Primary")
        self.send_button.setMinimumWidth(100)
        input_row.addWidget(self.input_box, 1)
        input_row.addWidget(self.send_button)
        root.addLayout(input_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Status")
        root.addWidget(self.status_label)

        self.send_button.clicked.connect(self._emit_input)
        QShortcut(
            QKeySequence("Ctrl+Return"),
            self,
            activated=self._emit_input,
        )
        self.settings_button.clicked.connect(
            self.settings_requested.emit
        )
        self.save_button.clicked.connect(
            self.checkpoint_requested.emit
        )
        self.launcher_button.clicked.connect(
            self.launcher_requested.emit
        )
        self.original_button.clicked.connect(
            lambda: self.onboarding_mode_requested.emit(
                "original"
            )
        )
        self.existing_button.clicked.connect(
            lambda: self.onboarding_mode_requested.emit(
                "existing"
            )
        )
        self.observer_button.clicked.connect(
            lambda: self.onboarding_mode_requested.emit(
                "observer"
            )
        )
        self.finalize_button.clicked.connect(
            self.onboarding_finalize_requested.emit
        )

    def set_session(self, event: Dict[str, Any]) -> None:
        self.needs_setup = bool(
            event.get("needs_setup", False)
        )
        self.session_label.setText(
            "{}  ·  {}".format(
                event.get("game_name", ""),
                event.get("game_id", ""),
            )
        )
        self.onboarding_frame.setVisible(
            self.needs_setup
        )
        self.save_button.setEnabled(
            not self.needs_setup
        )
        self.set_onboarding_state(
            event.get("onboarding", {})
        )

    def mark_setup_complete(self) -> None:
        self.needs_setup = False
        self.onboarding_frame.hide()
        self.save_button.setEnabled(True)
        self.set_status("온보딩 완료")

    def set_onboarding_state(
        self,
        state: Dict[str, Any],
    ) -> None:
        if not isinstance(state, dict):
            return
        phase = str(state.get("phase", ""))
        mode = state.get("player_character_mode")
        has_draft = bool(
            state.get("has_character_draft", False)
        )

        self.finalize_button.setEnabled(
            phase == "ready_to_finalize"
            or (
                mode == "original"
                and has_draft
            )
        )

    def show_reply(
        self,
        text: str,
        *,
        speaker: str = "DateGPT",
    ) -> None:
        self.speaker_label.setText(speaker)
        self.dialogue_text.setPlainText(text)

    def show_user_input(self, text: str) -> None:
        self.show_reply(text, speaker="나")

    def set_waiting(
        self,
        waiting: bool,
        status: str = "",
    ) -> None:
        self.send_button.setEnabled(not waiting)
        self.input_box.setEnabled(not waiting)
        self.original_button.setEnabled(not waiting)
        self.existing_button.setEnabled(not waiting)
        self.observer_button.setEnabled(not waiting)
        if waiting and status:
            self.set_status(status)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _emit_input(self) -> None:
        text = self.input_box.toPlainText().strip()
        if not text:
            return
        self.input_box.clear()
        self.send_requested.emit(text)


class SettingsDialog(QDialog):
    refresh_requested = Signal()
    model_requested = Signal(str, str)
    api_key_requested = Signal(str, str)
    api_key_clear_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DateGPT 설정")
        self.setMinimumWidth(520)
        self._snapshot: Dict[str, Any] = {}

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(
            ["openai", "anthropic"]
        )
        self.model_edit = QLineEdit()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(
            QLineEdit.EchoMode.Password
        )
        self.api_status = QLabel("미설정")
        self.api_status.setObjectName("Muted")

        form.addRow("모델 제공사", self.provider_combo)
        form.addRow("모델", self.model_edit)
        form.addRow("API key", self.api_key_edit)
        form.addRow("", self.api_status)
        root.addLayout(form)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("현재 설정 읽기")
        self.model_button = QPushButton("모델 저장")
        self.key_button = QPushButton("API key 저장")
        self.clear_key_button = QPushButton("API key 삭제")
        buttons.addWidget(self.refresh_button)
        buttons.addStretch(1)
        buttons.addWidget(self.model_button)
        buttons.addWidget(self.key_button)
        buttons.addWidget(self.clear_key_button)
        root.addLayout(buttons)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Status")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.refresh_button.clicked.connect(
            self.refresh_requested.emit
        )
        self.model_button.clicked.connect(
            self._emit_model
        )
        self.key_button.clicked.connect(
            self._emit_key
        )
        self.clear_key_button.clicked.connect(
            self._emit_clear_key
        )
        self.provider_combo.currentTextChanged.connect(
            self._update_api_status
        )

    def apply_snapshot(
        self,
        snapshot: Dict[str, Any],
    ) -> None:
        self._snapshot = dict(snapshot)
        supported = snapshot.get(
            "supported_providers",
            ["openai", "anthropic"],
        )
        current_provider = str(
            snapshot.get("provider", "openai")
        )

        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        self.provider_combo.addItems(
            [str(value) for value in supported]
        )
        index = self.provider_combo.findText(
            current_provider
        )
        if index >= 0:
            self.provider_combo.setCurrentIndex(index)
        self.provider_combo.blockSignals(False)

        self.model_edit.setText(
            str(snapshot.get("model", ""))
        )
        self.api_key_edit.clear()
        self._update_api_status()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _update_api_status(self) -> None:
        provider = self.provider_combo.currentText()
        keys = self._snapshot.get("api_keys", {})
        info = (
            keys.get(provider, {})
            if isinstance(keys, dict)
            else {}
        )
        if info.get("configured"):
            self.api_status.setText(
                "설정됨: {} ({})".format(
                    info.get("masked", ""),
                    info.get("source", ""),
                )
            )
        else:
            self.api_status.setText("미설정")

    def _emit_model(self) -> None:
        provider = self.provider_combo.currentText()
        model = self.model_edit.text().strip()
        if not model:
            self.set_status("모델명을 입력하세요.")
            return
        self.model_requested.emit(provider, model)

    def _emit_key(self) -> None:
        provider = self.provider_combo.currentText()
        key = self.api_key_edit.text().strip()
        if not key:
            self.set_status("API key를 입력하세요.")
            return
        self.api_key_requested.emit(provider, key)

    def _emit_clear_key(self) -> None:
        self.api_key_clear_requested.emit(
            self.provider_combo.currentText()
        )


class MainWindow(QMainWindow):
    def __init__(
        self,
        client: BackendClient,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.active_session: Dict[str, Any] = {}
        self._request_kinds: Dict[str, str] = {}

        self.setWindowTitle("DateGPT")
        self.resize(1280, 820)

        self.stack = QStackedWidget()
        self.launcher = LauncherPage()
        self.game = GamePage()
        self.stack.addWidget(self.launcher)
        self.stack.addWidget(self.game)
        self.setCentralWidget(self.stack)

        self.settings_dialog = SettingsDialog(self)

        self.debug_dock = QDockWidget(
            "Backend Debug",
            self,
        )
        self.debug_text = QPlainTextEdit()
        self.debug_text.setReadOnly(True)
        self.debug_dock.setWidget(self.debug_text)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.debug_dock,
        )
        self.debug_dock.hide()

        view_menu = self.menuBar().addMenu("보기")
        debug_action = QAction(
            "디버그 패널",
            self,
            checkable=True,
        )
        debug_action.toggled.connect(
            self.debug_dock.setVisible
        )
        self.debug_dock.visibilityChanged.connect(
            debug_action.setChecked
        )
        view_menu.addAction(debug_action)

        settings_action = QAction("설정", self)
        settings_action.triggered.connect(
            self.open_settings
        )
        self.menuBar().addAction(settings_action)

        self.setStatusBar(QStatusBar(self))

        self.launcher.refresh_requested.connect(
            self.refresh_cartridges
        )
        self.launcher.install_requested.connect(
            self.install_cartridge
        )
        self.launcher.scenario_changed.connect(
            self.refresh_game_instances
        )
        self.launcher.new_game_requested.connect(
            self.start_new_game
        )
        self.launcher.continue_requested.connect(
            self.continue_game
        )

        self.game.send_requested.connect(
            self.send_player_text
        )
        self.game.settings_requested.connect(
            self.open_settings
        )
        self.game.checkpoint_requested.connect(
            self.checkpoint
        )
        self.game.onboarding_mode_requested.connect(
            self.select_onboarding_mode
        )
        self.game.onboarding_finalize_requested.connect(
            self.finalize_onboarding
        )
        self.game.launcher_requested.connect(
            self.return_to_launcher
        )

        self.settings_dialog.refresh_requested.connect(
            self.refresh_model_settings
        )
        self.settings_dialog.model_requested.connect(
            self.set_model
        )
        self.settings_dialog.api_key_requested.connect(
            self.set_api_key
        )
        self.settings_dialog.api_key_clear_requested.connect(
            self.clear_api_key
        )

        self.client.event_received.connect(
            self._handle_event
        )
        self.client.debug_line.connect(
            self._append_debug
        )
        self.client.running_changed.connect(
            self._on_running_changed
        )
        self.client.fatal_error.connect(
            self._show_fatal_error
        )

    def _send(
        self,
        payload: Dict[str, Any],
        kind: str,
    ) -> Optional[str]:
        try:
            request_id = self.client.send(payload)
        except Exception as exc:
            self._show_fatal_error(str(exc))
            return None
        self._request_kinds[request_id] = kind
        return request_id

    def refresh_cartridges(self) -> None:
        self.launcher.set_status(
            "시나리오 목록을 읽는 중..."
        )
        self._send(
            {"type": "list_cartridges"},
            "list_cartridges",
        )

    def install_cartridge(self) -> None:
        source, ok = QInputDialog.getText(
            self,
            "시나리오 설치",
            "로컬 폴더 또는 GitHub repository/tree 주소:",
        )
        source = source.strip()
        if not ok or not source:
            return
        self.launcher.set_status(
            "시나리오를 설치하는 중..."
        )
        self._send(
            {
                "type": "install_cartridge",
                "source": source,
            },
            "install_cartridge",
        )

    def refresh_game_instances(
        self,
        cartridge: Dict[str, Any],
    ) -> None:
        game_name = str(
            cartridge.get("game_name", "")
        )
        if not game_name:
            return
        self._send(
            {
                "type": "list_game_instances",
                "game_name": game_name,
            },
            "list_game_instances",
        )

    def start_new_game(
        self,
        cartridge: Dict[str, Any],
    ) -> None:
        payload = self._open_session_payload(
            cartridge
        )
        payload["new_game"] = True
        self.launcher.set_status(
            "새 게임을 여는 중..."
        )
        self._send(payload, "open_session")

    def continue_game(
        self,
        cartridge: Dict[str, Any],
        game_id: str,
    ) -> None:
        payload = self._open_session_payload(
            cartridge
        )
        payload["game_id"] = game_id
        self.launcher.set_status(
            "기존 게임을 여는 중..."
        )
        self._send(payload, "open_session")

    @staticmethod
    def _open_session_payload(
        cartridge: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "type": "open_session",
            "game_name": str(
                cartridge.get("game_name", "")
            ),
        }
        build = cartridge.get("build_version")
        if build not in (None, ""):
            payload["build_version"] = str(build)
        return payload

    def open_settings(self) -> None:
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()
        self.refresh_model_settings()

    def refresh_model_settings(self) -> None:
        self.settings_dialog.set_status(
            "현재 설정을 읽는 중..."
        )
        self._send(
            {"type": "get_model_settings"},
            "settings",
        )

    def set_model(
        self,
        provider: str,
        model: str,
    ) -> None:
        self.settings_dialog.set_status(
            "모델 설정 저장 중..."
        )
        self._send(
            {
                "type": "set_model",
                "provider": provider,
                "model": model,
            },
            "settings",
        )

    def set_api_key(
        self,
        provider: str,
        api_key: str,
    ) -> None:
        self.settings_dialog.set_status(
            "API key 저장 중..."
        )
        self._send(
            {
                "type": "set_api_key",
                "provider": provider,
                "api_key": api_key,
            },
            "settings",
        )

    def clear_api_key(self, provider: str) -> None:
        self.settings_dialog.set_status(
            "API key 삭제 중..."
        )
        self._send(
            {
                "type": "clear_api_key",
                "provider": provider,
            },
            "settings",
        )

    def send_player_text(self, text: str) -> None:
        if not self.active_session:
            return
        self.game.show_user_input(text)
        self.game.set_waiting(
            True,
            "응답 대기 중...",
        )
        if self.active_session.get(
            "needs_setup",
            False,
        ):
            payload = {
                "type": "onboarding_turn",
                "text": text,
            }
            kind = "onboarding_turn"
        else:
            payload = {
                "type": "play",
                "text": text,
            }
            kind = "play"
        self._send(payload, kind)

    def select_onboarding_mode(
        self,
        mode: str,
    ) -> None:
        payload: Dict[str, Any] = {
            "type": "onboarding_select_mode",
            "mode": mode,
        }
        if mode == "existing":
            path, ok = QInputDialog.getText(
                self,
                "기존 캐릭터",
                "Distribution의 캐릭터 경로:",
                text="entities/",
            )
            path = path.strip()
            if not ok or not path:
                return
            payload["main_character"] = path

        self.game.set_waiting(
            True,
            "온보딩 모드 변경 중...",
        )
        self._send(payload, "onboarding_mode")

    def finalize_onboarding(self) -> None:
        self.game.set_waiting(
            True,
            "온보딩을 마무리하는 중...",
        )
        self._send(
            {"type": "onboarding_finalize"},
            "onboarding_finalize",
        )

    def checkpoint(self) -> None:
        if not self.active_session:
            return
        self.game.set_waiting(
            True,
            "현재 상태 저장 중...",
        )
        self._send(
            {"type": "checkpoint"},
            "checkpoint",
        )

    def return_to_launcher(self) -> None:
        self.stack.setCurrentWidget(
            self.launcher
        )
        self.refresh_cartridges()

    def _handle_event(
        self,
        event: Dict[str, Any],
    ) -> None:
        event_type = str(event.get("type", ""))
        request_id = str(
            event.get("request_id", "")
        )
        kind = self._request_kinds.get(
            request_id,
            "",
        )

        if event_type == "status":
            message = str(
                event.get("message", "처리 중...")
            )
            self.statusBar().showMessage(message)
            if self.stack.currentWidget() is self.game:
                self.game.set_status(message)
            else:
                self.launcher.set_status(message)
            return

        if event_type == "cartridge_list":
            self.launcher.set_cartridges(
                event.get("cartridges", [])
            )
            self.launcher.set_status("")
            self._finish_request(request_id)
            return

        if event_type == "cartridge_installed":
            cartridge = event.get("cartridge", {})
            self.launcher.set_status(
                "설치 완료: {}".format(
                    cartridge.get(
                        "game_name",
                        "(unknown)",
                    )
                )
            )
            self._finish_request(request_id)
            self.refresh_cartridges()
            return

        if event_type == "game_instance_list":
            self.launcher.set_game_ids(
                event.get("game_ids", [])
            )
            self._finish_request(request_id)
            return

        if event_type == "session_opened":
            self.active_session = dict(event)
            self.game.set_session(event)
            self.stack.setCurrentWidget(self.game)
            self.game.set_waiting(False)
            self._finish_request(request_id)
            if event.get("needs_setup", False):
                self.game.show_reply(
                    "새 게임 온보딩을 시작합니다.",
                    speaker="System",
                )
                self.game.set_waiting(
                    True,
                    "온보딩 시작 중...",
                )
                self._send(
                    {"type": "onboarding_start"},
                    "onboarding_start",
                )
            else:
                self.game.show_reply(
                    "기존 게임을 이어갑니다.",
                    speaker="System",
                )
                self.game.set_status("")
            return

        if event_type == "onboarding_state":
            state = event.get("state", {})
            self.game.set_onboarding_state(state)
            return

        if event_type == "session_setup_complete":
            self.active_session.update(event)
            self.active_session["needs_setup"] = False
            self.game.mark_setup_complete()
            self.game.set_waiting(False)
            self.game.show_reply(
                "온보딩이 완료되었습니다.",
                speaker="System",
            )
            self._finish_request(request_id)
            return

        if event_type == "model_settings":
            settings = event.get("settings", {})
            if isinstance(settings, dict):
                self.settings_dialog.apply_snapshot(
                    settings
                )
            return

        if event_type == "control_state":
            return

        if event_type == "checkpoint_complete":
            self.game.set_waiting(False)
            self.game.set_status(
                str(event.get("text", "저장 완료"))
            )
            self._finish_request(request_id)
            return

        if event_type == "reply":
            text = str(event.get("text", ""))
            if kind == "settings":
                self.settings_dialog.set_status(text)
                self.refresh_model_settings()
            elif kind in {
                "play",
                "onboarding_start",
                "onboarding_turn",
                "onboarding_mode",
            }:
                self.game.show_reply(text)
                onboarding = event.get("onboarding")
                if isinstance(onboarding, dict):
                    self.game.set_onboarding_state(
                        onboarding
                    )
                self.game.set_waiting(False)
                self.game.set_status("")
            else:
                self.statusBar().showMessage(text)
            self._finish_request(request_id)
            return

        if event_type == "error":
            message = str(
                event.get("message", "알 수 없는 오류")
            )
            code = str(event.get("code", "ERROR"))
            rendered = "{}: {}".format(code, message)

            if kind == "settings":
                self.settings_dialog.set_status(
                    rendered
                )
            elif self.stack.currentWidget() is self.game:
                self.game.set_waiting(False)
                self.game.set_status(rendered)
            else:
                self.launcher.set_status(rendered)

            self._finish_request(request_id)
            return

        if event_type == "instance_selection_required":
            self.launcher.set_game_ids(
                event.get("game_ids", [])
            )
            self.launcher.set_status(
                "이어할 플레이를 선택하세요."
            )
            self.stack.setCurrentWidget(
                self.launcher
            )
            self._finish_request(request_id)
            return

        if event_type in {
            "session_closed",
            "shutdown_complete",
        }:
            self._finish_request(request_id)
            return

    def _finish_request(self, request_id: str) -> None:
        if request_id:
            self._request_kinds.pop(
                request_id,
                None,
            )

    def _on_running_changed(
        self,
        running: bool,
    ) -> None:
        if running:
            self.statusBar().showMessage(
                "Backend connected"
            )
            self.refresh_cartridges()
            self.refresh_model_settings()
        else:
            self.statusBar().showMessage(
                "Backend stopped"
            )

    def _append_debug(self, line: str) -> None:
        self.debug_text.appendPlainText(line)

    def _show_fatal_error(self, message: str) -> None:
        QMessageBox.critical(
            self,
            "DateGPT backend 오류",
            message,
        )


