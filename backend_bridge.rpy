default backend_waiting = False
default backend_status = ""
default backend_reply = ""
default backend_error = ""
default backend_session = {}
default backend_controls = {}
default backend_model_settings = {}
default backend_onboarding = {}


transform backend_spinner:
    rotate 0
    linear 1.0 rotate 360
    repeat

screen backend_wait_screen(who="상대"):

    key "backend_event" action Function(handle_backend_events)

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
    import threading


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
    # EVENT / STATE
    # ============================================================

    config.keymap["backend_event"] = []

    backend_process = None
    backend_queue = queue.Queue()
    backend_handlers = {}
    backend_request_counter = 0
    backend_request_lock = threading.Lock()


    # ============================================================
    # HANDLER REGISTRATION
    # ============================================================

    def backend_handler(event_type):

        def decorator(func):
            backend_handlers[event_type] = func
            return func

        return decorator


    # ============================================================
    # REQUEST IDS
    # ============================================================

    def next_backend_request_id():

        global backend_request_counter

        with backend_request_lock:
            backend_request_counter += 1
            return "renpy-{}".format(
                backend_request_counter
            )


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

        renpy.invoke_in_thread(
            backend_stderr_reader
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
    # BACKGROUND READERS
    # ============================================================

    def backend_reader():

        for line in backend_process.stdout:

            try:
                msg = json.loads(line)
            except Exception as exc:
                msg = {
                    "type": "error",
                    "code": "PROTOCOL_ERROR",
                    "message": "backend JSON parse failed: {}".format(exc),
                    "recoverable": True,
                }

            backend_queue.put(msg)

            renpy.queue_event(
                "backend_event"
            )


    def backend_stderr_reader():

        for line in backend_process.stderr:
            line = line.rstrip()
            if line:
                renpy.log(
                    "[DateGPT backend] " + line
                )


    # ============================================================
    # SEND
    # ============================================================

    def send_backend(data):

        if backend_process is None:
            start_backend()

        payload = dict(data)

        if "request_id" not in payload:
            payload["request_id"] = (
                next_backend_request_id()
            )

        encoded = json.dumps(
            payload,
            ensure_ascii=False,
        )

        backend_process.stdin.write(
            encoded + "\n"
        )

        backend_process.stdin.flush()

        return payload["request_id"]


    def begin_backend_request(data):

        store.backend_waiting = True
        store.backend_status = "요청 전송 중..."
        store.backend_reply = ""
        store.backend_error = ""

        return send_backend(data)


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


    @backend_handler("session_opened")
    def handle_session_opened(msg):

        store.backend_session = dict(msg)
        store.backend_controls = dict(
            msg.get("controls", {})
        )
        store.backend_onboarding = dict(
            msg.get("onboarding", {})
        )
        store.backend_waiting = False
        return True


    @backend_handler("session_setup_complete")
    def handle_session_setup_complete(msg):

        store.backend_session.update(msg)
        store.backend_controls = dict(
            msg.get("controls", {})
        )
        if "onboarding" in msg:
            store.backend_onboarding = dict(
                msg.get("onboarding", {})
            )
        store.backend_waiting = False
        return True


    @backend_handler("session_state")
    def handle_session_state(msg):

        store.backend_session = dict(msg)
        if "controls" in msg:
            store.backend_controls = dict(
                msg.get("controls", {})
            )
        if "onboarding" in msg:
            store.backend_onboarding = dict(
                msg.get("onboarding", {})
            )
        store.backend_waiting = False
        return True


    @backend_handler("session_closed")
    def handle_session_closed(msg):

        store.backend_session = {}
        store.backend_waiting = False
        return True


    @backend_handler("instance_selection_required")
    def handle_instance_selection_required(msg):

        store.backend_session = dict(msg)
        store.backend_waiting = False
        return True


    @backend_handler("onboarding_state")
    def handle_onboarding_state(msg):

        store.backend_onboarding = dict(
            msg.get("state", {})
        )


    @backend_handler("control_state")
    def handle_control_state(msg):

        store.backend_controls = dict(
            msg.get("controls", {})
        )


    @backend_handler("model_settings")
    def handle_model_settings(msg):

        store.backend_model_settings = dict(
            msg.get("settings", {})
        )


    @backend_handler("checkpoint_complete")
    def handle_checkpoint_complete(msg):

        store.backend_reply = msg.get(
            "text",
            ""
        )
        store.backend_waiting = False
        return True


    @backend_handler("shutdown_complete")
    def handle_shutdown_complete(msg):

        store.backend_waiting = False
        return True
