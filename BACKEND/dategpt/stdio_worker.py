from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .protocol import BackendApplication


def _resource_root() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", "")
        if bundle_root:
            return Path(bundle_root).resolve()
    return Path(__file__).resolve().parents[2]


def _user_data_root() -> Path:
    override = os.environ.get(
        "DATEGPT_HOME",
        "",
    ).strip()
    if override:
        return Path(override).expanduser().resolve()

    home = Path.home()
    if sys.platform == "darwin":
        return (
            home
            / "Library"
            / "Application Support"
            / "DateGPT"
        )
    if os.name == "nt":
        appdata = os.environ.get(
            "APPDATA",
            "",
        ).strip()
        if appdata:
            return Path(appdata).expanduser().resolve() / "DateGPT"
        return (
            home
            / "AppData"
            / "Roaming"
            / "DateGPT"
        )
    xdg = os.environ.get(
        "XDG_DATA_HOME",
        "",
    ).strip()
    if xdg:
        return Path(xdg).expanduser().resolve() / "DateGPT"
    return home / ".local" / "share" / "DateGPT"


def _configure_frozen_runtime() -> Path:
    resource_root = _resource_root()
    if not getattr(sys, "frozen", False):
        return resource_root / "BACKEND"

    data_root = _user_data_root()
    data_root.mkdir(parents=True, exist_ok=True)

    defaults = {
        "DATEGPT_CONFIG_DIR": data_root / "config",
        "DATEGPT_SAVE_DIR": data_root / "games",
        "DATEGPT_RUNTIME_DIR": data_root / "runtime",
        "DATEGPT_CARTRIDGE_DIR": data_root / "cartridges",
        "DATEGPT_SOURCE_CACHE_DIR": data_root / "sources",
        "DATEGPT_PROMPT_DIR": resource_root / ".scaffolding",
    }
    for name, path in defaults.items():
        os.environ.setdefault(
            name,
            str(path),
        )

    return data_root / "_backend"


def _configure_stdio() -> None:
    if (
        sys.stdin is not None
        and hasattr(sys.stdin, "reconfigure")
    ):
        sys.stdin.reconfigure(encoding="utf-8")

    if (
        sys.stdout is not None
        and hasattr(sys.stdout, "reconfigure")
    ):
        sys.stdout.reconfigure(
            encoding="utf-8",
            line_buffering=True,
        )

    if (
        sys.stderr is not None
        and hasattr(sys.stderr, "reconfigure")
    ):
        sys.stderr.reconfigure(
            encoding="utf-8",
            line_buffering=True,
        )


def _debug(message: str) -> None:
    if sys.stderr is None:
        return
    print(
        "[protocol] {}".format(message),
        file=sys.stderr,
        flush=True,
    )


def _send(data: dict) -> None:
    if sys.stdout is None:
        raise RuntimeError(
            "backend stdout is unavailable"
        )
    _debug(
        "OUT type={} request_id={}".format(
            data.get("type"),
            data.get("request_id"),
        )
    )
    print(
        json.dumps(
            data,
            ensure_ascii=False,
        ),
        flush=True,
    )


def run() -> int:
    _configure_stdio()
    backend_dir = _configure_frozen_runtime()
    app = BackendApplication(
        backend_dir=backend_dir,
    )

    _debug(
        "READY backend_dir={} frozen={}".format(
            backend_dir,
            bool(getattr(sys, "frozen", False)),
        )
    )

    if sys.stdin is None:
        raise RuntimeError(
            "backend stdin is unavailable"
        )

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
            if not isinstance(msg, dict):
                raise ValueError(
                    "protocol message must be a JSON object"
                )

            msg_type = msg.get("type")
            _debug(
                "IN type={} request_id={}".format(
                    msg_type,
                    msg.get("request_id"),
                )
            )

            if msg_type == "shutdown":
                payload = {
                    "type": "shutdown_complete",
                }
                request_id = msg.get("request_id")
                if request_id is not None:
                    payload["request_id"] = request_id
                _send(payload)
                return 0

            for event in app.handle(
                msg,
                emit=_send,
            ):
                _send(event)

        except json.JSONDecodeError as exc:
            _send({
                "type": "error",
                "code": "PROTOCOL_ERROR",
                "message": "invalid JSON: {}".format(exc),
                "recoverable": True,
            })
        except Exception as exc:
            _debug(
                "{}: {}".format(
                    type(exc).__name__,
                    exc,
                )
            )
            _send({
                "type": "error",
                "code": "BACKEND_ERROR",
                "message": "{}: {}".format(
                    type(exc).__name__,
                    exc,
                ),
                "recoverable": True,
            })

    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
