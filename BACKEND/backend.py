import json
import sys
from pathlib import Path

from dategpt.protocol import BackendApplication


# stdout is protocol-only. Debug/log output must go to stderr or files.
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        line_buffering=True,
    )

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(
        encoding="utf-8",
        line_buffering=True,
    )


BACKEND_DIR = Path(__file__).resolve().parent
app = BackendApplication(
    backend_dir=BACKEND_DIR,
)


def send(data):
    print(
        json.dumps(
            data,
            ensure_ascii=False,
        ),
        flush=True,
    )


def handle(msg):
    msg_type = msg.get("type")

    if msg_type == "shutdown":
        request_id = msg.get("request_id")
        payload = {"type": "shutdown_complete"}
        if request_id is not None:
            payload["request_id"] = request_id
        send(payload)
        return False

    for event in app.handle(
        msg,
        emit=send,
    ):
        send(event)

    return True


def main():
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

            keep_running = handle(msg)
            if not keep_running:
                break

        except json.JSONDecodeError as exc:
            send({
                "type": "error",
                "code": "PROTOCOL_ERROR",
                "message": "invalid JSON: {}".format(exc),
                "recoverable": True,
            })
        except Exception as exc:
            print(
                "{}: {}".format(
                    type(exc).__name__,
                    exc,
                ),
                file=sys.stderr,
                flush=True,
            )
            send({
                "type": "error",
                "code": "BACKEND_ERROR",
                "message": "{}: {}".format(
                    type(exc).__name__,
                    exc,
                ),
                "recoverable": True,
            })


if __name__ == "__main__":
    main()
