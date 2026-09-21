import json
import sys

from dategpt.controls import ControlState
from dategpt.host import RuntimeHost


# pipe에서도 한글 인코딩을 명확히 맞춘다.
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        line_buffering=True,
    )


host = RuntimeHost(controls=ControlState())


def send(data):
    print(
        json.dumps(
            data,
            ensure_ascii=False,
        ),
        flush=True,
    )


def send_control_response(response):
    if response.controls is not None:
        send({
            "type": "control_state",
            "controls": response.controls,
        })

    send({
        "type": "reply",
        "text": response.message,
    })


def handle(msg):
    msg_type = msg.get("type")

    if msg_type == "shutdown":
        return False

    if msg_type == "ping":
        send({
            "type": "reply",
            "text": "pong — 백엔드 살아있음",
        })
        return True

    # Deterministic controls are always routed before any future LLM call.
    control_response = host.route_control(msg)
    if control_response.handled:
        send_control_response(control_response)
        return True

    if msg_type == "say":
        text = msg.get("text", "")

        send({
            "type": "status",
            "message": "메세지 처리중...",
        })

        # AgentRunner will replace this stub. The important boundary already
        # exists: controls above never consume an LLM call.
        send({
            "type": "reply",
            "text": "백엔드가 받음: {}".format(text),
        })
        return True

    send({
        "type": "error",
        "message": "알 수 없는 message type: {}".format(msg_type),
    })
    return True


def main():
    for line in sys.stdin:
        line = line.strip()

        if not line:
            continue

        try:
            msg = json.loads(line)
            keep_running = handle(msg)
            if not keep_running:
                break
        except Exception as exc:
            send({
                "type": "error",
                "message": "{}: {}".format(
                    type(exc).__name__,
                    exc,
                ),
            })


if __name__ == "__main__":
    main()
