default backend_waiting = False
default backend_status = ""
default backend_reply = ""
default backend_error = ""
default backend_session = {}
default backend_controls = {}
default backend_model_settings = {}
default backend_onboarding = {}
default backend_cartridge = {}
default backend_cartridges = []

# Development transport diagnostics.
default backend_debug_lines = []
default backend_last_request = ""
default backend_last_event = ""
default backend_request_started_at = 0.0


transform backend_spinner:
    rotate 0
    linear 1.0 rotate 360
    repeat


screen backend_wait_screen(who="상대"):

    # queue_event is still used for low-latency wakeups, but the timer makes
    # the bridge recover even if a custom event is lost or not delivered.
    key "backend_event" action Function(handle_backend_events)
    timer 0.10 action Function(poll_backend_wait) repeat True
    timer 0.10 action If(
        backend_waiting,
        NullAction(),
        Return()
    ) repeat True

    frame:
        xalign 0.5
        yalign 0.72
        xmaximum 1180
        padding (24, 18)

        vbox:
            spacing 8

            hbox:
                spacing 10

                text "◒":
                    size 26
                    at backend_spinner

                text "[who!q] · [backend_status!q]":
                    size 22

            if backend_last_request:
                text "OUT  [backend_last_request!q]":
                    size 15

            if backend_last_event:
                text "LAST [backend_last_event!q]":
                    size 15

            if backend_debug_lines:
                null height 4

                for line in backend_debug_lines[-10:]:
                    text "[line!q]":
                        size 14


init python:

    import subprocess
    import queue
    import json
    import os
    import threading
    import time


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
    # DEBUG
    # ============================================================

    def backend_debug(text):

        text = str(text).rstrip()

        if not text:
            return

        lines = list(store.backend_debug_lines)
        lines.append(text)
        store.backend_debug_lines = lines[-40:]


    def backend_payload_summary(payload):

        if not isinstance(payload, dict):
            return repr(payload)

        safe = dict(payload)

        # Never place raw API keys on the visible diagnostics screen.
        text_value = safe.get("text")
        if (
            isinstance(text_value, str)
            and text_value.startswith("!api")
        ):
            safe["text"] = "<api-key command redacted>"

        if "api_key" in safe:
            safe["api_key"] = "<redacted>"

        encoded = json.dumps(
            safe,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        if len(encoded) > 500:
            encoded = encoded[:497] + "..."

        return encoded


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

        store.backend_debug_lines = []
        backend_debug(
            "PYTHON {}".format(BACKEND_PYTHON)
        )
        backend_debug(
            "BACKEND {}".format(BACKEND_PATH)
        )

        try:
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
        except Exception as exc:
            backend_process = None
            store.backend_error = (
                "backend start failed: {}: {}".format(
                    type(exc).__name__,
                    exc,
                )
            )
            store.backend_waiting = False
            backend_debug(
                "START ERROR {}".format(
                    store.backend_error
                )
            )
            raise

        backend_debug(
            "PROCESS pid={}".format(
                backend_process.pid
            )
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

            try:
                send_backend({
                    "type": "shutdown"
                })
                backend_process.wait(timeout=1.0)

            except Exception:
                backend_process.terminate()

        backend_process = None


    # ============================================================
    # BACKGROUND READERS
    # ============================================================

    def backend_reader():

        process = backend_process

        try:
            for line in process.stdout:

                raw = line.rstrip("\r\n")

                try:
                    msg = json.loads(raw)
                except Exception as exc:
                    msg = {
                        "type": "error",
                        "code": "PROTOCOL_ERROR",
                        "message": (
                            "backend JSON parse failed: {} | raw={!r}"
                        ).format(
                            exc,
                            raw[:500],
                        ),
                        "recoverable": True,
                    }

                backend_queue.put(msg)

                try:
                    renpy.queue_event(
                        "backend_event"
                    )
                except Exception:
                    # The polling timer is the fallback transport wakeup.
                    pass

        finally:
            return_code = process.poll()
            backend_queue.put({
                "type": "_backend_eof",
                "return_code": return_code,
            })

            try:
                renpy.queue_event(
                    "backend_event"
                )
            except Exception:
                pass


    def backend_stderr_reader():

        process = backend_process

        for line in process.stderr:
            line = line.rstrip()

            if not line:
                continue

            renpy.log(
                "[DateGPT backend] " + line
            )

            backend_queue.put({
                "type": "_backend_debug",
                "stream": "stderr",
                "text": line,
            })

            try:
                renpy.queue_event(
                    "backend_event"
                )
            except Exception:
                pass


    # ============================================================
    # SEND
    # ============================================================

    def send_backend(data):

        if (
            backend_process is None
            or backend_process.poll() is not None
        ):
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

        store.backend_last_request = (
            backend_payload_summary(payload)
        )
        backend_debug(
            "OUT {}".format(
                store.backend_last_request
            )
        )

        try:
            backend_process.stdin.write(
                encoded + "\n"
            )
            backend_process.stdin.flush()
        except Exception as exc:
            store.backend_error = (
                "backend send failed: {}: {}".format(
                    type(exc).__name__,
                    exc,
                )
            )
            store.backend_waiting = False
            backend_debug(
                "SEND ERROR {}".format(
                    store.backend_error
                )
            )
            raise

        return payload["request_id"]


    def begin_backend_request(data):

        store.backend_waiting = True
        store.backend_status = "요청 전송 중..."
        store.backend_reply = ""
        store.backend_error = ""
        store.backend_last_event = ""
        store.backend_request_started_at = time.time()

        return send_backend(data)


    # ============================================================
    # POLLING / DISPATCH
    # ============================================================

    def poll_backend_wait():

        handle_backend_events()

        process = backend_process

        if (
            store.backend_waiting
            and process is not None
        ):
            return_code = process.poll()

            if return_code is not None:
                store.backend_error = (
                    "backend process exited with code {}".format(
                        return_code
                    )
                )
                store.backend_status = "백엔드 종료"
                store.backend_waiting = False
                backend_debug(
                    "PROCESS EXIT code={}".format(
                        return_code
                    )
                )

        if (
            store.backend_waiting
            and store.backend_request_started_at
        ):
            elapsed = (
                time.time()
                - store.backend_request_started_at
            )

            # Not a hard timeout: LLM calls may legitimately take longer.
            # This simply makes a silent stall visible.
            if elapsed >= 5.0:
                store.backend_status = (
                    "응답 대기 중 ({:.1f}s)".format(
                        elapsed
                    )
                )


    def handle_backend_events():

        completed = False

        while True:

            try:
                msg = backend_queue.get_nowait()

            except queue.Empty:
                break

            event_type = msg.get("type", "(missing)")
            store.backend_last_event = str(event_type)

            if event_type == "_backend_debug":
                backend_debug(
                    "ERR {}".format(
                        msg.get("text", "")
                    )
                )
                continue

            if event_type == "_backend_eof":
                return_code = msg.get(
                    "return_code"
                )
                backend_debug(
                    "EOF return_code={}".format(
                        return_code
                    )
                )

                if store.backend_waiting:
                    store.backend_error = (
                        "backend stdout closed"
                        if return_code is None
                        else (
                            "backend exited with code {}".format(
                                return_code
                            )
                        )
                    )
                    store.backend_waiting = False
                    completed = True

                continue

            backend_debug(
                "IN  {}".format(
                    backend_payload_summary(msg)
                )
            )

            handler = backend_handlers.get(
                event_type
            )

            if handler is None:
                backend_debug(
                    "UNHANDLED EVENT {}".format(
                        event_type
                    )
                )
                continue

            result = handler(msg)

            if result:
                completed = True

        return completed


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

        store.backend_status = "오류"
        store.backend_waiting = False

        return True


    @backend_handler("cartridge_installed")
    def handle_cartridge_installed(msg):

        store.backend_cartridge = dict(
            msg.get("cartridge", {})
        )
        store.backend_waiting = False
        return True


    @backend_handler("cartridge_list")
    def handle_cartridge_list(msg):

        store.backend_cartridges = list(
            msg.get("cartridges", [])
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
        store.backend_session["needs_setup"] = False
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
