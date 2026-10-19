"""Regenerate the README gallery: pip install -r scripts/requirements.txt first."""

import hashlib
import html
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageOps


START = "<!-- GALLERY:START -->"
END = "<!-- GALLERY:END -->"
FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def generate(root):
    readme = root / "README.md"
    original = readme.read_bytes().decode("utf-8")
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError("README must contain exactly one pair of gallery markers")
    start = original.index(START) + len(START)
    end = original.index(END)
    if start > end:
        raise ValueError("Gallery markers are in the wrong order")
    if not (root / "wallpapers").is_dir():
        raise FileNotFoundError("wallpapers directory is missing")

    gallery = root / ".gallery"
    gallery.mkdir(exist_ok=True)
    sources = sorted(
        (path for path in (root / "wallpapers").rglob("*")
         if path.is_file() and path.suffix.lower() in FORMATS),
        key=lambda path: (path.name, path.relative_to(root).as_posix()),
    )
    cells = []
    expected = set()
    for source in sources:
        relative = source.relative_to(root).as_posix()
        # Include rendering settings so changing them invalidates cached thumbnails.
        digest = hashlib.sha256(b"jpeg-384x216-center-q75-v2\0" + relative.encode("utf-8") + b"\0")
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        thumbnail = gallery / (digest.hexdigest() + ".jpg")
        expected.add(thumbnail.name)
        if not thumbnail.exists():
            with Image.open(source) as image:
                image = ImageOps.exif_transpose(image)
                image = ImageOps.fit(
                    image.convert("RGB"), (384, 216), Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
                image.save(thumbnail, quality=75, optimize=True)
        cells.append(
            f'    <td><a href="{quote(relative, safe="/")}">'
            f'<img src=".gallery/{thumbnail.name}" alt="{html.escape(source.name, quote=True)}" '
            f'width="384" height="216"></a></td>'
        )

    lines = ["", "<table>"]
    for offset in range(0, len(cells), 3):
        lines.extend(["  <tr>", *cells[offset:offset + 3], "  </tr>"])
    lines.extend(["</table>", ""])
    updated = original[:start] + "\n".join(lines) + original[end:]
    if updated != original:
        readme.write_bytes(updated.encode("utf-8"))
    for thumbnail in gallery.glob("*.jpg"):
        if thumbnail.name not in expected:
            thumbnail.unlink()


if __name__ == "__main__":
    generate(Path(__file__).resolve().parents[1])
