from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QProcess, Signal


class BackendClient(QObject):
    """Signal-driven JSONL transport for the DateGPT backend worker.

    Source mode launches this desktop entrypoint again with
    --backend-worker under the current Python interpreter. Frozen mode launches
    the packaged DateGPT executable itself with --backend-worker, so no external
    Python installation is required.
    """

    event_received = Signal(object)
    debug_line = Signal(str)
    running_changed = Signal(bool)
    fatal_error = Signal(str)

    def __init__(
        self,
        *,
        entrypoint_path: Optional[Path] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.frozen = bool(
            getattr(sys, "frozen", False)
        )
        self.program_path = Path(
            sys.executable
        ).resolve()

        if self.frozen:
            self.entrypoint_path = None
            arguments = ["--backend-worker"]
            self.worker_label = (
                "{} --backend-worker".format(
                    self.program_path
                )
            )
        else:
            path = (
                Path(entrypoint_path)
                if entrypoint_path is not None
                else Path(__file__).resolve().parent
                / "main.py"
            )
            self.entrypoint_path = (
                path.expanduser().resolve()
            )
            arguments = [
                str(self.entrypoint_path),
                "--backend-worker",
            ]
            self.worker_label = (
                "{} {} --backend-worker".format(
                    self.program_path,
                    self.entrypoint_path,
                )
            )

        self.process = QProcess(self)
        self.process.setProgram(
            str(self.program_path)
        )
        self.process.setArguments(arguments)

        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._request_counter = 0
        self._backend_ready = False
        self._expected_shutdown = False
        self._recent_stderr: List[str] = []

        self.process.started.connect(self._on_started)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(
            self._on_process_error
        )
        self.process.readyReadStandardOutput.connect(
            self._read_stdout
        )
        self.process.readyReadStandardError.connect(
            self._read_stderr
        )

    @property
    def is_running(self) -> bool:
        return (
            self.process.state()
            != QProcess.ProcessState.NotRunning
        )

    @property
    def is_ready(self) -> bool:
        return (
            self._backend_ready
            and self.process.state()
            == QProcess.ProcessState.Running
        )

    def start(self) -> None:
        if self.is_running:
            return

        self._backend_ready = False
        self._expected_shutdown = False
        self._recent_stderr.clear()

        if (
            not self.frozen
            and self.entrypoint_path is not None
            and not self.entrypoint_path.exists()
        ):
            self.fatal_error.emit(
                "desktop entrypoint를 찾을 수 없습니다: {}".format(
                    self.entrypoint_path
                )
            )
            return

        self.debug_line.emit(
            "START {}".format(
                self.worker_label
            )
        )
        self.process.start()

    def send(self, payload: Dict[str, Any]) -> str:
        if not self.is_ready:
            raise RuntimeError(
                self._not_ready_message()
            )

        message = dict(payload)
        request_id = message.get("request_id")
        if request_id is None:
            self._request_counter += 1
            request_id = "qt-{}".format(
                self._request_counter
            )
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

        written = self.process.write(
            (encoded + "\n").encode("utf-8")
        )
        if written < 0:
            raise RuntimeError(
                "backend write failed\nWorker: {}{}".format(
                    self.worker_label,
                    self._stderr_suffix(),
                )
            )
        return str(request_id)

    def shutdown(self) -> None:
        self._expected_shutdown = True
        if not self.is_running:
            return

        try:
            if self.is_ready:
                self.send({"type": "shutdown"})
                self.process.waitForFinished(700)
        except Exception:
            pass

        if self.is_running:
            self.process.terminate()
            self.process.waitForFinished(500)
        if self.is_running:
            self.process.kill()

    def _on_started(self) -> None:
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
        was_ready = self._backend_ready
        self._backend_ready = False
        if was_ready:
            self.running_changed.emit(False)

        self.debug_line.emit(
            "PROCESS finished code={} status={}".format(
                exit_code,
                exit_status.name,
            )
        )

        if self._expected_shutdown:
            return

        self.fatal_error.emit(
            self._finished_message(
                exit_code,
                exit_status,
            )
        )

    def _on_process_error(
        self,
        error: QProcess.ProcessError,
    ) -> None:
        message = (
            "QProcess error {}: {}\n"
            "Worker: {}{}"
        ).format(
            error.name,
            self.process.errorString(),
            self.worker_label,
            self._stderr_suffix(),
        )
        self.debug_line.emit(message)
        if not self._expected_shutdown:
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
                "백엔드 stdout JSON 파싱 실패: {}".format(
                    exc
                )
            )
            self.debug_line.emit(
                "BAD STDOUT " + line
            )
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
        self._recent_stderr.append(line)
        if len(self._recent_stderr) > 20:
            del self._recent_stderr[:-20]
        self.debug_line.emit(
            "ERR " + line
        )

        if (
            not self._backend_ready
            and line.startswith(
                "[protocol] READY "
            )
        ):
            self._backend_ready = True
            self.running_changed.emit(True)

    def _stderr_suffix(self) -> str:
        if not self._recent_stderr:
            return ""
        return (
            "\n\nBackend stderr:\n"
            + "\n".join(
                self._recent_stderr[-12:]
            )
        )

    def _not_ready_message(self) -> str:
        state = self.process.state()
        if state == QProcess.ProcessState.Starting:
            status = "backend worker is starting"
        elif state == QProcess.ProcessState.Running:
            status = (
                "backend worker started but is not ready"
            )
        else:
            status = "backend worker is not running"

        return "{}\nWorker: {}{}".format(
            status,
            self.worker_label,
            self._stderr_suffix(),
        )

    def _finished_message(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> str:
        return (
            "DateGPT backend worker exited before it was usable.\n"
            "exit_code={} status={}\n"
            "Worker: {}{}"
        ).format(
            exit_code,
            exit_status.name,
            self.worker_label,
            self._stderr_suffix(),
        )


def _redact_payload(
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    safe = dict(payload)
    if "api_key" in safe:
        safe["api_key"] = "<redacted>"

    text = safe.get("text")
    if (
        isinstance(text, str)
        and text.lstrip().casefold().startswith(
            (
                "!api_key",
                "!api키",
                "!apikey",
            )
        )
    ):
        safe["text"] = (
            "<api-key command redacted>"
        )
    return safe
