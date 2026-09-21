define a = Character("테스트")


label start:

    "백엔드를 시작한다."

    $ start_backend()

    "먼저 ping 테스트."

    $ begin_backend_request({
        "type": "ping"
    })

    call screen backend_wait_screen

    if backend_error:

        "백엔드 오류: [backend_error!q]"

    else:

        a "[backend_reply!q]"


    "이번에는 문자열을 보내보자."

    $ user_input = renpy.input(
        "아무 말이나 입력:",
        length=100,
    )

    $ user_input = user_input.strip()

    if not user_input:
        $ user_input = "안녕"


    $ begin_backend_request({
        "type": "say",
        "text": user_input,
    })

    call screen backend_wait_screen


    if backend_error:

        "백엔드 오류: [backend_error!q]"

    else:

        a "[backend_reply!q]"


    "테스트 완료."

    return


# 앱 자체를 종료할 때 backend도 정리.
label quit:

    $ stop_backend()

    return