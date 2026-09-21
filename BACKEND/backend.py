import sys
import json
import time


# pipe에서도 한글 인코딩을 명확히 맞춘다.
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        line_buffering=True,
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
        return False


    if msg_type == "ping":

        send({
            "type": "status",
            "message": "ping 처리중..."
        })

        time.sleep(3)

        send({
            "type": "reply",
            "text": "pong — 백엔드 살아있음"
        })

        return True


    if msg_type == "say":

        text = msg.get("text", "")

        # 즉시 frontend로 중간 상태 전달.
        send({
            "type": "status",
            "message": "메세지 처리중..."
        })

        # LLM 호출 흉내.
        time.sleep(3)

        send({
            "type": "reply",
            "text": "백엔드가 받음: {}".format(text)
        })

        return True


    send({
        "type": "error",
        "message": "알 수 없는 message type: {}".format(
            msg_type
        )
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

        except Exception as e:

            send({
                "type": "error",
                "message": "{}: {}".format(
                    type(e).__name__,
                    e,
                )
            })


if __name__ == "__main__":
    main()