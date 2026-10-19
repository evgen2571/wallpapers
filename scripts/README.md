The gallery uses Python 3.12+ and Pillow for development only. The installer
needs neither.

```sh
python -m pip install -r scripts/requirements.txt
python -m unittest discover -s tests -v
python scripts/generate_gallery.py
```

The generator reads JPEG, PNG, WebP, GIF, BMP, and TIFF images under
`wallpapers/` (including subdirectories). Animated images use their first frame.
It creates 384×216 JPEG previews with a centered 16:9 crop, resizing small images
as needed. Originals are never modified. Content and relative paths determine
cache filenames; changing an image or renaming it replaces its preview. Keep
`.gallery/` for generated files only. If rendering settings change, update the
cache version in the script.

The workflow runs after changes to originals or generator configuration on
`main`, or manually on the selected branch. The repository must allow GitHub
Actions to push commits to that branch. Generated commits do not match the
workflow's path filters.
