#!/usr/bin/env bash
set -euo pipefail

REPO="evgen2571/wallpapers"
BRANCH="main"
DEST="${1:-$HOME/Pictures/Wallpapers}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "[1/3] Downloading wallpaper archive..."

curl --fail --location \
	"https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" \
	--output "$tmp/archive.tar.gz"

echo "[2/3] Extracting archive..."
tar -xzf "$tmp/archive.tar.gz" -C "$tmp"

source="$tmp/wallpapers-$BRANCH/wallpapers"
if [[ ! -d "$source" ]]; then
	echo "Error: archive contains no wallpapers directory." >&2
	exit 1
fi
find "$source" ! -type d -print0 >"$tmp/files"
files=()
while IFS= read -r -d '' file; do
	files+=("$file")
done <"$tmp/files"
total=${#files[@]}
installed=0

echo "[3/3] Installing wallpapers..."
mkdir -p "$DEST"
shopt -s dotglob nullglob
for wallpaper in "$source"/*; do
	cp -a "$wallpaper" "$DEST/"
	for file in "${files[@]}"; do
		if [[ "$file" == "$wallpaper" || "$file" == "$wallpaper/"* ]]; then
			installed=$((installed + 1))
		fi
	done
	if [[ -t 1 ]]; then
		printf '\rInstalling wallpapers: %d/%d' "$installed" "$total"
	fi
done
if [[ -t 1 ]]; then
	printf '\n'
fi
printf 'Installed %d/%d wallpapers.\n' "$installed" "$total"

echo "Done! Wallpapers installed to: $DEST"
