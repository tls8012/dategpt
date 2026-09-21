define backend_voice = Character("DateGPT")


default dev_cartridge_source = ""
default dev_prompt_dir = ""


init python:

    def normalize_dev_path(value):
        value = (value or "").strip()
        if not value:
            return ""
        return os.path.abspath(
            os.path.expanduser(value)
        )


    def default_dev_cartridge_source():
        return normalize_dev_path(
            os.environ.get(
                "DATEGPT_TEST_CARTRIDGE_SOURCE",
                "",
            )
        )


    def default_dev_prompt_dir():
        return normalize_dev_path(
            os.environ.get(
                "DATEGPT_PROMPT_DIR",
                "",
            )
        )


label start:

    "DateGPT 개발용 텍스트 하네스."

    $ start_backend()

    # ------------------------------------------------------------
    # Cartridge source
    # ------------------------------------------------------------

    if not dev_cartridge_source:
        $ dev_cartridge_source = default_dev_cartridge_source()

    if not dev_cartridge_source:
        "테스트 카트리지 폴더를 입력해."
        "예: /path/to/chatgpt_cartridges/datellm"

        $ dev_cartridge_source = renpy.input(
            "카트리지 경로:",
            length=1024,
        ).strip()

        $ dev_cartridge_source = normalize_dev_path(
            dev_cartridge_source
        )

    # ------------------------------------------------------------
    # Shared prompt scaffolding
    # ------------------------------------------------------------

    if not dev_prompt_dir:
        $ dev_prompt_dir = default_dev_prompt_dir()

    if not dev_prompt_dir:
        "공용 prompt scaffolding 폴더를 입력해."
        "예: /path/to/chatgpt-animevisualnovel/scaffolding"

        $ dev_prompt_dir = renpy.input(
            "프롬프트 경로:",
            length=1024,
        ).strip()

        $ dev_prompt_dir = normalize_dev_path(
            dev_prompt_dir
        )

    if not dev_cartridge_source:
        "카트리지 경로가 비어 있어서 종료한다."
        jump dategpt_shutdown

    if not dev_prompt_dir:
        "프롬프트 경로가 비어 있어서 종료한다."
        jump dategpt_shutdown

    # ------------------------------------------------------------
    # Install cartridge
    # ------------------------------------------------------------

    "카트리지를 로컬 라이브러리에 설치/확인한다."

    $ begin_backend_request({
        "type": "install_cartridge",
        "source_path": dev_cartridge_source,
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

    # ------------------------------------------------------------
    # Open the single active session
    # ------------------------------------------------------------

label dategpt_open_session:

    $ open_payload = {
        "type": "open_session",
        "game_name": mounted_game_name,
        "prompt_path": dev_prompt_dir,
    }

    if mounted_build_version:
        $ open_payload["build_version"] = mounted_build_version

    $ begin_backend_request(open_payload)

    call screen backend_wait_screen("backend")

    if backend_error:
        "세션 열기 오류: [backend_error!q]"
        jump dategpt_shutdown

    # Multiple existing GAME_IDs are the only case that needs a choice.
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

        if chosen_game_id.casefold() == "new":

            $ begin_backend_request({
                "type": "open_session",
                "game_name": mounted_game_name,
                "build_version": mounted_build_version,
                "prompt_path": dev_prompt_dir,
                "new_game": True,
            })

        else:

            $ begin_backend_request({
                "type": "open_session",
                "game_name": mounted_game_name,
                "build_version": mounted_build_version,
                "prompt_path": dev_prompt_dir,
                "game_id": chosen_game_id,
            })

        call screen backend_wait_screen("backend")

        if backend_error:
            "세션 선택 오류: [backend_error!q]"
            jump dategpt_shutdown

    "세션이 열렸다."
    "GAME: [backend_session.get('game_name', '')!q]"
    "GAME_ID: [backend_session.get('game_id', '')!q]"

    if backend_session.get("needs_setup", False):
        "새 게임 온보딩 상태다."
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


# 앱 자체를 종료할 때 backend도 정리.
label quit:

    $ stop_backend()

    return
