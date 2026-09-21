from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QProcess, Signal


class BackendClient(QObject):
    """Signal-driven JSONL transport for the existing DateGPT backend.

    The desktop frontend deliberately keeps backend.py as a child process.
    QProcess owns stdin/stdout/stderr integration, so no polling thread or
    Python queue is required on the frontend side.
    """

    event_received = Signal(object)
    debug_line = Signal(str)
    running_changed = Signal(bool)
    fatal_error = Signal(str)

    def __init__(
        self,
        backend_path: Path,
        *,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.backend_path = Path(backend_path).expanduser().resolve()
        self.python_path = Path(
            sys.executable
        ).resolve()
        self.process = QProcess(self)
        self.process.setProgram(str(self.python_path))
        self.process.setArguments([str(self.backend_path)])

        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._request_counter = 0

        self.process.started.connect(self._on_started)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_process_error)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)

    @property
    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def start(self) -> None:
        if self.is_running:
            return
        if not self.backend_path.exists():
            self.fatal_error.emit(
                "backend.py를 찾을 수 없습니다: {}".format(
                    self.backend_path
                )
            )
            return
        self.debug_line.emit(
            "START {} {}".format(
                self.python_path,
                self.backend_path,
            )
        )
        self.process.start()

    def send(self, payload: Dict[str, Any]) -> str:
        if not self.is_running:
            raise RuntimeError("DateGPT backend is not running")

        message = dict(payload)
        request_id = message.get("request_id")
        if request_id is None:
            self._request_counter += 1
            request_id = "qt-{}".format(self._request_counter)
            message["request_id"] = request_id

        encoded = json.dumps(
            message,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self.debug_line.emit(
            "OUT {}".format(
                json.dumps(
                    _redact_payload(message),
                    ensure_ascii=False,
                )
            )
        )
        self.process.write((encoded + "\n").encode("utf-8"))
        return str(request_id)

    def shutdown(self) -> None:
        if not self.is_running:
            return
        try:
            self.send({"type": "shutdown"})
            self.process.waitForFinished(500)
        except Exception:
            pass
        if self.is_running:
            self.process.terminate()
            self.process.waitForFinished(300)
        if self.is_running:
            self.process.kill()

    def _on_started(self) -> None:
        self.running_changed.emit(True)
        self.debug_line.emit(
            "PROCESS started pid={}".format(
                self.process.processId()
            )
        )

    def _on_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self.running_changed.emit(False)
        self.debug_line.emit(
            "PROCESS finished code={} status={}".format(
                exit_code,
                exit_status.name,
            )
        )

    def _on_process_error(
        self,
        error: QProcess.ProcessError,
    ) -> None:
        message = "QProcess error {}: {}".format(
            error.name,
            self.process.errorString(),
        )
        self.debug_line.emit(message)
        self.fatal_error.emit(message)

    def _read_stdout(self) -> None:
        chunk = bytes(
            self.process.readAllStandardOutput()
        ).decode("utf-8", errors="replace")
        self._stdout_buffer += chunk
        self._stdout_buffer = self._consume_lines(
            self._stdout_buffer,
            self._handle_stdout_line,
        )

    def _read_stderr(self) -> None:
        chunk = bytes(
            self.process.readAllStandardError()
        ).decode("utf-8", errors="replace")
        self._stderr_buffer += chunk
        self._stderr_buffer = self._consume_lines(
            self._stderr_buffer,
            self._handle_stderr_line,
        )

    @staticmethod
    def _consume_lines(
        buffer: str,
        handler,
    ) -> str:
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line:
                handler(line)
        return buffer

    def _handle_stdout_line(self, line: str) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            self.fatal_error.emit(
                "백엔드 stdout JSON 파싱 실패: {}".format(exc)
            )
            self.debug_line.emit("BAD STDOUT " + line)
            return

        if not isinstance(event, dict):
            self.fatal_error.emit(
                "백엔드 이벤트가 JSON object가 아닙니다."
            )
            return

        self.debug_line.emit(
            "IN  {}".format(
                json.dumps(
                    _redact_payload(event),
                    ensure_ascii=False,
                )
            )
        )
        self.event_received.emit(event)

    def _handle_stderr_line(self, line: str) -> None:
        self.debug_line.emit("ERR " + line)


def _redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(payload)
    if "api_key" in safe:
        safe["api_key"] = "<redacted>"
    text = safe.get("text")
    if (
        isinstance(text, str)
        and text.lstrip().casefold().startswith(
            ("!api_key", "!api키", "!apikey")
        )
    ):
        safe["text"] = "<api-key command redacted>"
    return safe
