import unittest

from dategpt.sources import parse_github_source_url


class GitHubSourceTests(unittest.TestCase):
    def test_tree_url_parses_repo_ref_and_subpath(self):
        source = parse_github_source_url(
            "https://github.com/tls8012/chatgpt_cartridges/tree/main/datellm"
        )
        self.assertEqual(source.owner, "tls8012")
        self.assertEqual(source.repo, "chatgpt_cartridges")
        self.assertEqual(source.ref, "main")
        self.assertEqual(source.subpath, "datellm")
        self.assertEqual(
            source.clone_url,
            "https://github.com/tls8012/chatgpt_cartridges.git",
        )

    def test_repo_root_defaults_to_main(self):
        source = parse_github_source_url(
            "https://github.com/tls8012/chatgpt-animevisualnovel.git"
        )
        self.assertEqual(source.ref, "main")
        self.assertEqual(source.subpath, "")

    def test_non_github_url_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_github_source_url(
                "https://example.com/repo"
            )

    def test_embedded_credentials_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_github_source_url(
                "https://user:token@github.com/owner/repo"
            )


if __name__ == "__main__":
    unittest.main()
