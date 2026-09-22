import unittest

from pydantic import ValidationError

from dategpt.presentation import VNResponse, coerce_vn_response


class PresentationTests(unittest.TestCase):
    def test_structured_response_keeps_order_and_plain_text(self):
        response = VNResponse.model_validate({
            "segments": [
                {
                    "kind": "narration",
                    "speaker": "",
                    "text": "복도 끝에서 발소리가 멎었다.",
                },
                {
                    "kind": "dialogue",
                    "speaker": "ChatGPT",
                    "text": "늦어서 미안해.",
                    "assets": [
                        "bg.classroom.evening",
                        "chatgpt.smile",
                    ],
                },
                {
                    "kind": "dialogue",
                    "speaker": "Claude",
                    "text": "나는 방금 왔어.",
                },
            ]
        })

        self.assertEqual(
            response.plain_text(),
            (
                "복도 끝에서 발소리가 멎었다.\n"
                "ChatGPT: 늦어서 미안해.\n"
                "Claude: 나는 방금 왔어."
            ),
        )
        self.assertEqual(
            response.public_segments()[1]["speaker"],
            "ChatGPT",
        )
        self.assertEqual(
            response.public_segments()[1]["assets"],
            [
                "bg.classroom.evening",
                "chatgpt.smile",
            ],
        )

    def test_dialogue_requires_speaker(self):
        with self.assertRaises(ValidationError):
            VNResponse.model_validate({
                "segments": [
                    {
                        "kind": "dialogue",
                        "speaker": "",
                        "text": "안녕.",
                    }
                ]
            })

    def test_assets_default_empty_and_are_normalized(self):
        response = VNResponse.model_validate({
            "segments": [
                {
                    "kind": "narration",
                    "speaker": "",
                    "text": "창밖에 비가 내렸다.",
                    "assets": [
                        " bg.rain ",
                        "bg.rain",
                        "",
                        "chatgpt.window",
                    ],
                },
                {
                    "kind": "dialogue",
                    "speaker": "ChatGPT",
                    "text": "비 오네.",
                },
            ]
        })

        self.assertEqual(
            response.segments[0].assets,
            ["bg.rain", "chatgpt.window"],
        )
        self.assertEqual(
            response.segments[1].assets,
            [],
        )
        self.assertFalse(
            response.segments[1].clear_characters
        )

    def test_clear_characters_is_preserved(self):
        response = VNResponse.model_validate({
            "segments": [
                {
                    "kind": "narration",
                    "text": "두 사람은 복도를 떠났다.",
                    "clear_characters": True,
                }
            ]
        })
        self.assertTrue(
            response.segments[0].clear_characters
        )
        self.assertTrue(
            response.public_segments()[0][
                "clear_characters"
            ]
        )

    def test_non_dialogue_speaker_is_cleared(self):
        response = coerce_vn_response({
            "segments": [
                {
                    "kind": "narration",
                    "speaker": "Narrator",
                    "text": "비가 내렸다.",
                }
            ]
        })
        self.assertEqual(
            response.public_segments()[0]["speaker"],
            "",
        )


if __name__ == "__main__":
    unittest.main()
