import html
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from urllib.parse import quote

from PIL import Image

from scripts.generate_gallery import END, START, generate


REPO = Path(__file__).resolve().parents[1]


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "wallpapers").mkdir()
        self.prefix = "Description\n\n## Installation\nKeep this.\n\n## Gallery\n" + START
        self.suffix = END + "\n\n## Credits\nKeep these too.\n"
        (self.root / "README.md").write_text(self.prefix + "\nold gallery\n" + self.suffix)

    def image(self, name, size=(800, 400), color="red"):
        path = self.root / "wallpapers" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color).save(path)
        return path

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in [self.root / "README.md", *sorted((self.root / ".gallery").glob("*.jpg"))]}

    def test_layout_formats_links_and_originals(self):
        names = ['z tall.png', 'A wide.JPG', 'same.png', 'same.jpg', 'a & "<#%?雪.png']
        sizes = [(400, 1200), (1200, 400), (600, 600), (800, 400), (500, 250)]
        for name, size in zip(names, sizes):
            self.image(name, size)
        for extension in ["webp", "gif", "bmp", "tiff", "jpeg"]:
            self.image("extra." + extension)
        (self.root / "wallpapers" / "ignore.txt").write_text("not an image")
        originals = {p: p.read_bytes() for p in (self.root / "wallpapers").iterdir()}
        generate(self.root)
        readme = (self.root / "README.md").read_text()
        self.assertTrue(readme.startswith(self.prefix))
        self.assertTrue(readme.endswith(self.suffix))
        rows = re.findall(r"<tr>(.*?)</tr>", readme, re.S)
        self.assertEqual([row.count("<td>") for row in rows], [3, 3, 3, 1])
        entries = re.findall(r'<a href="([^"]+)"><img src="([^"]+)" alt="([^"]*)"', readme)
        self.assertEqual(len(entries), 10)
        self.assertEqual([html.unescape(alt) for _, _, alt in entries], sorted(p.name for p in originals if p.suffix != ".txt"))
        self.assertEqual(len({src for _, src, _ in entries}), 10)
        for href, src, alt in entries:
            name = html.unescape(alt)
            self.assertEqual(href, quote("wallpapers/" + name, safe="/"))
            with Image.open(self.root / src) as thumb:
                self.assertEqual(thumb.size, (384, 216))
                self.assertEqual(thumb.format, "JPEG")
        self.assertEqual(originals, {p: p.read_bytes() for p in originals})

    def test_cache_add_remove_rename_and_content_changes(self):
        first = self.image("first.png")
        generate(self.root)
        initial = self.snapshot()
        first.touch()
        generate(self.root)
        self.assertEqual(initial, self.snapshot())
        second = self.image("second.png")
        generate(self.root)
        self.assertEqual((self.root / "README.md").read_text().count("<td>"), 2)
        self.assertEqual((self.root / "README.md").read_text().count("<tr>"), 1)
        for name, value in initial.items():
            if name != "README.md":
                self.assertEqual(self.snapshot()[name], value)
        first.unlink()
        second.rename(second.with_name("renamed #.png"))
        generate(self.root)
        self.assertEqual(len(list((self.root / ".gallery").glob("*.jpg"))), 1)
        self.assertFalse(set(initial) - {"README.md"} & set(self.snapshot()))
        before_change = self.snapshot()
        source = self.root / "wallpapers" / "renamed #.png"
        stamp = source.stat()
        self.image(source.name, color="blue")
        os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        generate(self.root)
        self.assertNotEqual(set(before_change), set(self.snapshot()))
        final = self.snapshot()
        generate(self.root)
        self.assertEqual(final, self.snapshot())
        source.unlink()
        generate(self.root)
        self.assertEqual(list((self.root / ".gallery").iterdir()), [])
        self.assertNotIn("<tr>", (self.root / "README.md").read_text())

    def test_nested_duplicate_names_small_images_and_transparency(self):
        self.image("a/small.png", (100, 200))
        self.image("b/small.png", (200, 100))
        Image.new("RGBA", (600, 300), (0, 0, 255, 100)).save(self.root / "wallpapers" / "alpha.png")
        generate(self.root)
        sizes = []
        for path in (self.root / ".gallery").glob("*.jpg"):
            with Image.open(path) as image:
                sizes.append(image.size)
        self.assertCountEqual(sizes, [(384, 216)] * 3)

    def test_previews_crop_from_center_without_modifying_originals(self):
        cases = [
            ((1200, 216), (408, 0, 792, 216)),
            ((384, 1000), (0, 392, 384, 608)),
            ((384, 384), (0, 84, 384, 300)),
        ]
        for index, (size, center) in enumerate(cases):
            image = Image.new("RGB", size, "red")
            image.paste("green", center)
            image.save(self.root / "wallpapers" / f"{index}.png")
        originals = {p: p.read_bytes() for p in (self.root / "wallpapers").iterdir()}
        generate(self.root)
        for path in (self.root / ".gallery").glob("*.jpg"):
            with Image.open(path) as thumbnail:
                self.assertEqual(thumbnail.size, (384, 216))
                for point in [(10, 10), (192, 108), (373, 205)]:
                    red, green, blue = thumbnail.getpixel(point)
                    self.assertGreater(green, 100)
                    self.assertLess(red, 20)
                    self.assertLess(blue, 20)
        self.assertEqual(originals, {p: p.read_bytes() for p in originals})

    def test_invalid_markers_fail_without_changing_readme(self):
        for content in ["no markers", END + START, START + START + END]:
            with self.subTest(content=content):
                (self.root / "README.md").write_text(content)
                with self.assertRaises(ValueError):
                    generate(self.root)
                self.assertEqual((self.root / "README.md").read_text(), content)
                self.assertFalse((self.root / ".gallery").exists())

    def test_installer_copies_only_originals_without_python(self):
        self.image("original space.png")
        generate(self.root)
        archive = self.root / "archive.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for name in ["wallpapers", ".gallery", "README.md"]:
                tar.add(self.root / name, arcname="wallpapers-main/" + name)
        commands = self.root / "bin"
        commands.mkdir()
        for command in ["mktemp", "rm", "tar", "gzip", "mkdir", "cp"]:
            (commands / command).symlink_to(shutil.which(command))
        curl = commands / "curl"
        curl.write_text('#!/bin/sh\nwhile [ "$1" != "--output" ]; do shift; done\nshift\ncp "$TEST_ARCHIVE" "$1"\n')
        curl.chmod(0o755)
        destination = self.root / "installed"
        result = subprocess.run(
            [shutil.which("bash"), str(REPO / "install.sh"), str(destination)],
            env={**os.environ, "PATH": str(commands), "TEST_ARCHIVE": str(archive)},
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([p.name for p in destination.iterdir()], ["original space.png"])
        self.assertEqual((destination / "original space.png").read_bytes(),
                         (self.root / "wallpapers" / "original space.png").read_bytes())

    def test_missing_directory_or_corrupt_image_does_not_replace_gallery(self):
        self.image("good.png")
        generate(self.root)
        before = self.snapshot()
        shutil.rmtree(self.root / "wallpapers")
        with self.assertRaises(FileNotFoundError):
            generate(self.root)
        self.assertEqual(before, self.snapshot())
        (self.root / "wallpapers").mkdir()
        (self.root / "wallpapers" / "broken.png").write_bytes(b"not a PNG")
        with self.assertRaises(OSError):
            generate(self.root)
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
