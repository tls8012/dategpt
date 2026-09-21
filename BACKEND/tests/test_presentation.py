import unittest

from dategpt.presentation import parse_presentation


class PresentationTests(unittest.TestCase):
    def test_splits_narration_and_character_dialogue(self):
        segments = parse_presentation(
            "복도 끝에서 발소리가 멎었다. 모두가 문을 바라봤다.\n\n"
            "ChatGPT: 늦어서 미안해. 오래 기다렸어?\n"
            "Claude: 나는 방금 왔어."
        )

        self.assertEqual(
            [item["kind"] for item in segments],
            [
                "narration",
                "narration",
                "dialogue",
                "dialogue",
                "dialogue",
            ],
        )
        self.assertEqual(
            [item["speaker"] for item in segments[-3:]],
            ["ChatGPT", "ChatGPT", "Claude"],
        )
        self.assertEqual(
            segments[0]["text"],
            "복도 끝에서 발소리가 멎었다.",
        )
        self.assertEqual(
            segments[3]["text"],
            "오래 기다렸어?",
        )

    def test_plain_text_falls_back_to_narration(self):
        segments = parse_presentation("문장이 하나뿐이다")
        self.assertEqual(
            segments,
            [
                {
                    "kind": "narration",
                    "speaker": "",
                    "text": "문장이 하나뿐이다",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
