import unittest

from dategpt.scenarios import CharacterManifestIndex


class CharacterManifestIndexTests(unittest.TestCase):
    def test_exact_name_alias_and_role_lookup(self):
        source = """
# CHARACTER MANIFEST
- 설연 | aliases: 달마대사의 재림 | roles: 청하문 장문인의 딸, 검객 | path: entities/characters/설연.md
- 남궁휘 | roles: 무림맹주 | path: entities/characters/남궁휘.md
"""
        index = CharacterManifestIndex.from_texts(
            distribution_text=source,
        )

        self.assertEqual(
            index.resolve_unique("설연").path,
            "entities/characters/설연.md",
        )
        self.assertEqual(
            index.resolve_unique(
                "달마대사의 재림"
            ).path,
            "entities/characters/설연.md",
        )
        self.assertEqual(
            index.resolve_unique("무림맹주").path,
            "entities/characters/남궁휘.md",
        )

    def test_save_overlay_updates_public_identifiers(self):
        source = """
- 설연 | aliases: 달마대사의 재림 | roles: 검객 | path: entities/characters/설연.md
"""
        save = """
- 설연 | aliases: 소연 | path: entities/characters/설연.md
- 새별 | aliases: 별이 | roles: 객잔 직원 | path: entities/characters/새별.md
"""
        index = CharacterManifestIndex.from_texts(
            distribution_text=source,
            save_text=save,
        )

        self.assertIsNone(
            index.resolve_unique(
                "달마대사의 재림"
            )
        )
        self.assertEqual(
            index.resolve_unique("소연").path,
            "entities/characters/설연.md",
        )
        self.assertEqual(
            index.resolve_unique("검객").path,
            "entities/characters/설연.md",
        )
        self.assertEqual(
            index.resolve_unique("별이").path,
            "entities/characters/새별.md",
        )

    def test_ambiguous_public_key_is_not_guessed(self):
        source = """
- 전대 검마 | aliases: 검마 | path: entities/characters/old.md
- 현 검마 | aliases: 검마 | path: entities/characters/current.md
"""
        index = CharacterManifestIndex.from_texts(
            distribution_text=source,
        )

        self.assertEqual(
            len(index.lookup("검마")),
            2,
        )
        self.assertIsNone(
            index.resolve_unique("검마")
        )


if __name__ == "__main__":
    unittest.main()
