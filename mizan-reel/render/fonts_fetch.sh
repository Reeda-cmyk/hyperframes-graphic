#!/usr/bin/env bash
# Fetch the exact font files used by the renderer (woff2 from @fontsource -> ttf).
set -e
cd "$(dirname "$0")/.."
mkdir -p assets/fonts .fonts-tmp && cd .fonts-tmp
[ -f package.json ] || npm init -y >/dev/null
npm i --no-fund --no-audit @fontsource/inter @fontsource/playfair-display \
  @fontsource/cairo @fontsource/amiri
python3 - <<'PY'
import os
from fontTools.ttLib import TTFont
src = {
 "Cairo-Arabic": "@fontsource/cairo/files/cairo-arabic-400-normal.woff2",
 "Cairo-Arabic-Bold": "@fontsource/cairo/files/cairo-arabic-700-normal.woff2",
 "Cairo-Latin": "@fontsource/cairo/files/cairo-latin-400-normal.woff2",
 "Cairo-Latin-Bold": "@fontsource/cairo/files/cairo-latin-700-normal.woff2",
 "Amiri-Arabic": "@fontsource/amiri/files/amiri-arabic-400-normal.woff2",
 "Inter": "@fontsource/inter/files/inter-latin-400-normal.woff2",
 "Inter-Bold": "@fontsource/inter/files/inter-latin-700-normal.woff2",
 "Inter-Black": "@fontsource/inter/files/inter-latin-900-normal.woff2",
 "Playfair-Med": "@fontsource/playfair-display/files/playfair-display-latin-500-normal.woff2",
 "Playfair-Bold": "@fontsource/playfair-display/files/playfair-display-latin-700-normal.woff2",
}
out = "../assets/fonts"
os.makedirs(out, exist_ok=True)
for name, path in src.items():
    f = TTFont("node_modules/" + path)
    f.flavor = None
    f.save(os.path.join(out, name + ".ttf"))
print("fonts ->", os.path.abspath(out))
PY
