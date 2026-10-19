#!/usr/bin/env bash
set -euo pipefail

REPO="evgen2571/wallpapers"
BRANCH="main"
DEST="${1:-$HOME/Pictures/Wallpapers}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "Downloading wallpapers..."

curl --fail --location --progress-bar \
	"https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" \
	--output "$tmp/archive.tar.gz"

echo "Extracting wallpapers..."
tar -xzf "$tmp/archive.tar.gz" -C "$tmp"

echo "Installing wallpapers..."
mkdir -p "$DEST"
cp -a "$tmp/wallpapers-$BRANCH/wallpapers/." "$DEST/"

echo "Done! Wallpapers installed to: $DEST"
