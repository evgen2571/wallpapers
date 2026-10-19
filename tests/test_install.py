import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import os
from pathlib import Path
import pty
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest


REPO = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.files = {
            "one space.jpg": b"first wallpaper",
            "two #雪.png": b"second wallpaper",
            "nested/line\nbreak.jpg": b"third wallpaper",
            ".hidden.png": b"fourth wallpaper",
        }
        archive = self.root / "archive.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for name, content in self.files.items():
                entry = tarfile.TarInfo("wallpapers-main/wallpapers/" + name)
                entry.size = len(content)
                entry.mode = 0o640
                tar.addfile(entry, io.BytesIO(content))
            entry = tarfile.TarInfo("wallpapers-main/.gallery/preview.jpg")
            tar.addfile(entry, io.BytesIO())
        self.payload = archive.read_bytes()
        self.include_length = True
        test = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/fail":
                    self.send_error(503)
                    return
                self.send_response(200)
                if test.include_length:
                    self.send_header("Content-Length", str(len(test.payload)))
                self.end_headers()
                self.wfile.write(test.payload)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        commands = self.root / "bin"
        commands.mkdir()
        for command in ["mktemp", "rm", "tar", "gzip", "mkdir", "cp", "find"]:
            (commands / command).symlink_to(shutil.which(command))
        curl = commands / "curl"
        curl.write_text(
            f'#!{shutil.which("bash")}\n'
            'args=("$@")\n'
            'for index in "${!args[@]}"; do\n'
            '  if [[ "${args[$index]}" == https://github.com/* ]]; then\n'
            '    args[$index]="$TEST_URL"\n'
            '  fi\n'
            'done\n'
            'exec "$REAL_CURL" "${args[@]}"\n'
        )
        curl.chmod(0o755)
        self.destination = self.root / "installed wallpapers"
        self.environment = {
            **os.environ, "PATH": str(commands), "REAL_CURL": shutil.which("curl"),
            "TEST_URL": f"http://127.0.0.1:{server.server_port}/archive",
            "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1",
        }

    def install(self, **kwargs):
        return subprocess.run(
            [shutil.which("bash"), str(REPO / "install.sh"), str(self.destination)],
            env=self.environment, stderr=subprocess.PIPE, timeout=10, **kwargs,
        )

    def test_byte_meter_and_file_count_preserve_originals_and_nested_names(self):
        self.destination.mkdir()
        (self.destination / "existing.jpg").write_bytes(b"keep this")
        result = self.install(stdout=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"Received", result.stderr)
        self.assertIn(b"Speed", result.stderr)
        self.assertIn(b"[1/3]", result.stdout)
        self.assertIn(b"[2/3]", result.stdout)
        self.assertIn(b"[3/3]", result.stdout)
        self.assertIn(b"4/4", result.stdout)
        self.assertNotIn(b"\r", result.stdout)
        for name, content in self.files.items():
            path = self.destination / name
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.destination / "existing.jpg").read_bytes(), b"keep this")
        self.assertFalse((self.destination / ".gallery").exists())

    def test_interactive_counter_updates_in_place(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        try:
            result = self.install(stdout=slave)
        finally:
            os.close(slave)
        output = bytearray()
        with contextlib.suppress(OSError):
            while chunk := os.read(master, 4096):
                output.extend(chunk)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"\rInstalling wallpapers: 1/4", output)
        self.assertIn(b"\rInstalling wallpapers: 4/4", output)

    def test_failed_download_never_starts_installing(self):
        self.environment["TEST_URL"] = self.environment["TEST_URL"].replace("/archive", "/fail")
        result = self.install(stdout=subprocess.PIPE, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("[3/3]", result.stdout)
        self.assertNotIn("Done!", result.stdout)
        self.assertFalse(self.destination.exists())

    def test_failed_copy_is_not_counted_as_installed(self):
        cp = self.root / "bin" / "cp"
        cp.unlink()
        cp.write_text('#!/bin/sh\necho "copy failed" >&2\nexit 1\n')
        cp.chmod(0o755)
        result = self.install(stdout=subprocess.PIPE, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("4/4", result.stdout)
        self.assertNotIn("Done!", result.stdout)

    def test_byte_meter_works_without_a_known_download_size(self):
        self.include_length = False
        result = self.install(stdout=subprocess.PIPE, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Received", result.stderr)
        self.assertIn("4/4", result.stdout)

    def test_missing_wallpaper_directory_fails_before_installation(self):
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w:gz"):
            pass
        self.payload = payload.getvalue()
        result = self.install(stdout=subprocess.PIPE, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no wallpapers directory", result.stderr)
        self.assertNotIn("Done!", result.stdout)
        self.assertFalse(self.destination.exists())

    def test_empty_wallpaper_directory_reports_zero_installed(self):
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w:gz") as tar:
            entry = tarfile.TarInfo("wallpapers-main/wallpapers")
            entry.type = tarfile.DIRTYPE
            tar.addfile(entry)
        self.payload = payload.getvalue()
        result = self.install(stdout=subprocess.PIPE, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0/0", result.stdout)
        self.assertEqual(list(self.destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
