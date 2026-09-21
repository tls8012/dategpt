define backend_voice = Character("DateGPT")


default dev_cartridge_source = ""
default dev_prompt_dir = ""


init python:

    def is_github_source(value):
        return (
            (value or "")
            .strip()
            .casefold()
            .startswith("https://github.com/")
        )


    def normalize_dev_source(value):
        value = (value or "").strip()
        if not value:
            return ""
        if is_github_source(value):
            return value
        return os.path.abspath(
            os.path.expanduser(value)
        )


    def default_dev_cartridge_source():
        return normalize_dev_source(
            os.environ.get(
                "DATEGPT_TEST_CARTRIDGE_SOURCE",
                "",
            )
        )


    def default_dev_prompt_dir():
        value = os.environ.get(
            "DATEGPT_PROMPT_DIR",
            "",
        ).strip()
        if not value:
            return ""
        return os.path.abspath(
            os.path.expanduser(value)
        )


label start:

    "DateGPT 개발용 텍스트 하네스."

    $ start_backend()

    if not dev_cartridge_source:
        $ dev_cartridge_source = default_dev_cartridge_source()

    if not dev_cartridge_source:
        "테스트 카트리지 소스를 입력해."
        "로컬 폴더 또는 GitHub tree 링크를 사용할 수 있다."
        "예: https://github.com/tls8012/chatgpt_cartridges/tree/main/datellm"

        $ dev_cartridge_source = renpy.input(
            "카트리지 소스:",
            length=2048,
        ).strip()

        $ dev_cartridge_source = normalize_dev_source(
            dev_cartridge_source
        )

    if not dev_cartridge_source:
        "카트리지 소스가 비어 있어서 종료한다."
        jump dategpt_shutdown

    if not dev_prompt_dir:
        $ dev_prompt_dir = default_dev_prompt_dir()

    "카트리지를 로컬 라이브러리에 설치/확인한다."

    $ begin_backend_request({
        "type": "install_cartridge",
        "source": dev_cartridge_source,
    })

    call screen backend_wait_screen("backend")

    if backend_error:
        "카트리지 설치 오류: [backend_error!q]"
        jump dategpt_shutdown

    $ mounted_game_name = backend_cartridge.get(
        "game_name",
        "",
    )
    $ mounted_build_version = backend_cartridge.get(
        "build_version",
        "",
    )

    if not mounted_game_name:
        "카트리지 정보가 돌아오지 않았다."
        jump dategpt_shutdown

    "카트리지: [mounted_game_name!q] / build [mounted_build_version!q]"

label dategpt_open_session:

    $ open_payload = {
        "type": "open_session",
        "game_name": mounted_game_name,
    }

    if mounted_build_version:
        $ open_payload["build_version"] = mounted_build_version

    if dev_prompt_dir:
        $ open_payload["prompt_path"] = dev_prompt_dir

    $ begin_backend_request(open_payload)

    call screen backend_wait_screen("backend")

    if backend_error:
        "세션 열기 오류: [backend_error!q]"
        jump dategpt_shutdown

    if backend_session.get("type") == "instance_selection_required":

        "기존 플레이가 여러 개 있다."

        python:
            game_ids = backend_session.get("game_ids", [])
            for game_id in game_ids:
                renpy.say(
                    backend_voice,
                    "GAME_ID: {}".format(game_id),
                )

        $ chosen_game_id = renpy.input(
            "계속할 GAME_ID 입력. 새 게임이면 new:",
            length=128,
        ).strip()

        $ reopen_payload = {
            "type": "open_session",
            "game_name": mounted_game_name,
        }

        if mounted_build_version:
            $ reopen_payload["build_version"] = mounted_build_version

        if dev_prompt_dir:
            $ reopen_payload["prompt_path"] = dev_prompt_dir

        if chosen_game_id.casefold() == "new":
            $ reopen_payload["new_game"] = True
        else:
            $ reopen_payload["game_id"] = chosen_game_id

        $ begin_backend_request(reopen_payload)

        call screen backend_wait_screen("backend")

        if backend_error:
            "세션 선택 오류: [backend_error!q]"
            jump dategpt_shutdown

    $ session_game_name = backend_session.get(
        "game_name",
        "",
    )
    $ session_game_id = backend_session.get(
        "game_id",
        "",
    )

    "세션이 열렸다."
    "GAME: [session_game_name!q]"
    "GAME_ID: [session_game_id!q]"

    if backend_session.get("needs_setup", False):
        "새 게임 온보딩 상태다."
        "공용 scaffolding은 원본 prompt repo에서 자동으로 동기화된다."
        "먼저 모델/API 키를 설정해도 되고, 바로 대화를 시작해도 된다."
        "예: !모델, !모델 openai 모델명, !api_key openai 키, !새캐릭터"
    else:
        "기존 게임을 이어간다."

    "종료하려면 /quit 를 입력해."

    jump dategpt_text_loop


label dategpt_text_loop:

    $ user_input = renpy.input(
        ">",
        length=4000,
    ).strip()

    if not user_input:
        jump dategpt_text_loop

    if user_input.casefold() in {
        "/quit",
        "/exit",
    }:
        jump dategpt_shutdown

    $ begin_backend_request({
        "type": "say",
        "text": user_input,
    })

    call screen backend_wait_screen("DateGPT")

    if backend_error:

        "ERROR: [backend_error!q]"

    elif backend_reply:

        backend_voice "[backend_reply!q]"

    elif backend_onboarding.get("phase") == "complete":

        "온보딩이 완료됐다. 이제 일반 플레이 입력을 받는다."

    else:

        "요청은 처리됐지만 출력 텍스트는 없었다."

    jump dategpt_text_loop


label dategpt_shutdown:

    $ stop_backend()
    "DateGPT backend 종료."
    return


label quit:

    $ stop_backend()
    return
