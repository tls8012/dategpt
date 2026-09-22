from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "desktop"
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))

from backend_client import packaged_worker_path


class PackagedWorkerPathTests(unittest.TestCase):
    def test_macos_uses_sibling_worker(self):
        executable = Path(
            "/Applications/DateGPT.app/Contents/MacOS/DateGPT"
        )
        self.assertEqual(
            packaged_worker_path(
                executable,
                platform="darwin",
            ),
            Path(
                "/Applications/DateGPT.app/Contents/MacOS/DateGPTWorker"
            ),
        )

    def test_windows_uses_sibling_worker_exe(self):
        executable = Path(
            "C:/DateGPT/DateGPT.exe"
        )
        result = packaged_worker_path(
            executable,
            platform="win32",
        )
        self.assertEqual(
            result.name,
            "DateGPTWorker.exe",
        )
        self.assertEqual(
            result.parent.name,
            "DateGPT",
        )


if __name__ == "__main__":
    unittest.main()
