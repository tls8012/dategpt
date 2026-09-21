default backend_waiting = False
default backend_status = ""
default backend_reply = ""
default backend_error = ""


transform backend_spinner:
    rotate 0
    linear 1.0 rotate 360
    repeat

screen backend_wait_screen(who="상대"):

    # backend 이벤트는 계속 여기서 받는다.
    key "backend_event" action Function(handle_backend_events)

    # 기존 대사창 위쪽/안쪽에 붙는 작은 상태 표시.
    hbox:
        xalign 0.5
        yalign 0.82

        spacing 10

        text "◒":
            size 26
            at backend_spinner

        text "[who!q] · 생각하고 있습니다...":
            size 22

init python:

    import subprocess
    import queue
    import json
    import os


    # ============================================================
    # CONFIG
    # ============================================================

    PROJECT_DIR = os.path.dirname(config.gamedir)

    BACKEND_PATH = os.path.join(
        PROJECT_DIR,
        "game",
        "BACKEND",
        "backend.py",
    )

    BACKEND_PYTHON = os.path.join(
        PROJECT_DIR,
        "game",
        "BACKEND",
        "datevenv",
        "bin",
        "python3",
    )


    # ============================================================
    # EVENT
    # ============================================================

    config.keymap["backend_event"] = []


    # ============================================================
    # STATE
    # ============================================================

    backend_process = None
    backend_queue = queue.Queue()

    backend_handlers = {}


    # ============================================================
    # HANDLER REGISTRATION
    # ============================================================

    def backend_handler(event_type):

        def decorator(func):
            backend_handlers[event_type] = func
            return func

        return decorator


    # ============================================================
    # PROCESS
    # ============================================================

    def start_backend():

        global backend_process

        if (
            backend_process is not None
            and backend_process.poll() is None
        ):
            return

        backend_process = subprocess.Popen(
            [
                BACKEND_PYTHON,
                BACKEND_PATH,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

        renpy.invoke_in_thread(
            backend_reader
        )


    def stop_backend():

        global backend_process

        if backend_process is None:
            return

        if backend_process.poll() is None:

            send_backend({
                "type": "shutdown"
            })

            try:
                backend_process.wait(timeout=1.0)

            except:
                backend_process.terminate()

        backend_process = None


    # ============================================================
    # BACKGROUND READER
    # ============================================================

    def backend_reader():

        for line in backend_process.stdout:

            msg = json.loads(line)

            backend_queue.put(msg)

            renpy.queue_event(
                "backend_event"
            )


    # ============================================================
    # SEND
    # ============================================================

    def send_backend(data):

        payload = json.dumps(
            data,
            ensure_ascii=False,
        )

        backend_process.stdin.write(
            payload + "\n"
        )

        backend_process.stdin.flush()


    def begin_backend_request(data):

        store.backend_waiting = True
        store.backend_status = "요청 전송 중..."
        store.backend_reply = ""
        store.backend_error = ""

        send_backend(data)


    # ============================================================
    # DISPATCH
    # ============================================================

    def handle_backend_events():

        completed = False

        while True:

            try:
                msg = backend_queue.get_nowait()

            except queue.Empty:
                break

            event_type = msg.get("type")

            handler = backend_handlers.get(
                event_type
            )

            if handler is None:
                continue

            result = handler(msg)

            if result:
                completed = True


        if completed:
            return True

        return None


    # ============================================================
    # HANDLERS
    # ============================================================

    @backend_handler("status")
    def handle_status(msg):

        store.backend_status = msg.get(
            "message",
            "처리 중..."
        )


    @backend_handler("reply")
    def handle_reply(msg):

        store.backend_reply = msg.get(
            "text",
            ""
        )

        store.backend_waiting = False

        return True


    @backend_handler("error")
    def handle_error(msg):

        store.backend_error = msg.get(
            "message",
            ""
        )

        store.backend_waiting = False

        return True