import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "desktop/macos/backend_bootstrap.py"
TEMP_ROOT = Path(os.environ.get("GENEA_QA_DIR", "")).resolve()


def setUpModule():
    if (not os.environ.get("GENEA_QA_DIR") or
            not TEMP_ROOT.is_relative_to((ROOT / "tmp").resolve()) or
            not (TEMP_ROOT / ".codex-tmp").is_file()):
        raise RuntimeError("Set GENEA_QA_DIR to this task\'s marked directory inside project tmp/.")


class DesktopBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="backend-test-", dir=TEMP_ROOT)
        self.base = Path(self.temp.name)
        (self.base / ".codex-tmp").write_text("Created by test_desktop_backend.py.\n")
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.stdin.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if not process.stdin.closed:
                process.stdin.close()
            process.stdout.close()
            process.stderr.close()
        self.temp.cleanup()

    def launch(self, name, experimental=False):
        data = self.base / name
        data.mkdir()
        args = [sys.executable, "-I", "-B", "-u", "-c",
                "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));sys.argv.pop(0);runpy.run_path(sys.argv[0],run_name='__main__')",
                str(ROOT), str(BOOTSTRAP), "--data-dir", str(data)]
        if experimental:
            args.append("--experimental-default")
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        ready, _, _ = select.select([process.stdout], [], [], 10)
        self.assertTrue(ready, "backend failed to announce ready")
        line = process.stdout.readline()
        self.assertTrue(line, "backend exited before ready")
        message = json.loads(line)
        self.assertEqual(message["status"], "ready")
        self.assertGreater(message["port"], 0)
        return process, message["url"], data

    def request(self, url, path, payload=None):
        request = Request(url + path)
        if payload is not None:
            request = Request(url + path, data=json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    def test_two_families_have_distinct_ports_and_isolated_edits(self):
        first, a, data_a = self.launch("a")
        second, b, data_b = self.launch("b")
        self.assertNotEqual(a, b)
        self.request(a, "/api/generations", {"placement": "first", "name": "Test generation"})
        self.assertEqual(len(self.request(a, "/api/workspace")["generations"]), 1)
        self.assertEqual(len(self.request(b, "/api/workspace")["generations"]), 0)
        self.assertTrue((data_a / "workspace.json").is_file())
        self.assertNotEqual(data_a, data_b)
        first.stdin.close()
        self.assertEqual(first.wait(timeout=5), 0)
        self.assertIsNone(second.poll())

    def test_saved_experimental_setting_overrides_first_launch_default(self):
        process, url, data = self.launch("settings", experimental=True)
        self.assertTrue(self.request(url, "/api/config")["experimental_features_enabled"])
        self.request(url, "/api/config", {"experimental_features_enabled": False})
        process.stdin.close()
        self.assertEqual(process.wait(timeout=5), 0)
        # Relaunch using existing data, preserving settings.
        args = [sys.executable, "-I", "-B", "-u", "-c",
                "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));sys.argv.pop(0);runpy.run_path(sys.argv[0],run_name='__main__')",
                str(ROOT), str(BOOTSTRAP), "--data-dir", str(data), "--experimental-default"]
        again = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        self.processes.append(again)
        self.assertTrue(select.select([again.stdout], [], [], 10)[0])
        new_url = json.loads(again.stdout.readline())["url"]
        self.assertFalse(self.request(new_url, "/api/config")["experimental_features_enabled"])

    def test_sigterm_stops_backend_and_logs_never_pollute_stdout(self):
        process, url, _ = self.launch("signal")
        self.request(url, "/api/workspace")
        process.send_signal(signal.SIGTERM)
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(process.stdout.read(), "")
        self.assertIn("GET /api/workspace", process.stderr.read())


if __name__ == "__main__":
    unittest.main()
