#!/usr/bin/env bash
# Download the corpus PDF (CC BY-NC-SA 4.0, OpenStax) and verify the snapshot hash.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw
URL="https://assets.openstax.org/oscms-prodcms/media/documents/Introduction_to_Python_Programming-WEB.pdf"
OUT="data/raw/Introduction_to_Python_Programming-WEB.pdf"
[ -f "$OUT" ] || curl -fL -o "$OUT" "$URL"
EXPECTED="e1298e4fcfe541a8fc3bb786c5756d3d2be8e6ffc07997f1bc1e0ac270be383d"
ACTUAL="$(shasum -a 256 "$OUT" | cut -d' ' -f1)"
if [ "$ACTUAL" != "$EXPECTED" ]; then
  echo "WARNING: sha256 differs from the snapshot used in the report ($ACTUAL). OpenStax may have updated the PDF; page numbers/evidence may shift." >&2
  exit 1
fi
echo "OK: $OUT matches snapshot sha256"
