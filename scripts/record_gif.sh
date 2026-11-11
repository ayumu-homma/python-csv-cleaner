#!/usr/bin/env bash
# 実コマンドの端末操作を asciinema で録り、agg でループ GIF にする。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT/docs/screenshots"
CAST="$OUT_DIR/clean-demo.cast"
OUT_GIF="$OUT_DIR/clean-demo.gif"
PROOF="${PROOF_GIF:-/workspace/plans/images/proof/python-csv-clean-demo.gif}"
export TERM="${TERM:-xterm-256color}"
export PATH="/home/box/.local/bin:/tmp/venv-ascii/bin:$PATH"

mkdir -p "$OUT_DIR" /workspace/plans/images/proof

# 幅を抑えて GitHub 上でも文字が読めるようにする
rm -f "$CAST"
asciinema rec "$CAST" \
  --command "$ROOT/scripts/demo_session.sh" \
  --overwrite \
  --idle-time-limit 1.2 \
  --cols 92 \
  --rows 26 \
  --quiet

# TTC でも読めるか試し、ダメならシステムフォントディレクトリを追加
set +e
agg \
  --font-dir /tmp/fonts-mono \
  --font-family "Noto Sans Mono CJK JP" \
  --font-size 15 \
  --line-height 1.28 \
  --theme monokai \
  --fps-cap 12 \
  --idle-time-limit 0.8 \
  --last-frame-duration 2 \
  --speed 1.15 \
  "$CAST" "$OUT_GIF"
rc=$?
set -e
if [[ $rc -ne 0 || ! -s "$OUT_GIF" ]]; then
  echo "agg with CJK font failed (rc=$rc), retrying with DejaVu + font-dir" >&2
  agg \
    --font-dir /usr/share/fonts/opentype/noto \
    --font-dir /usr/share/fonts \
    --font-family "DejaVu Sans Mono,Noto Sans Mono CJK JP,Noto Sans CJK JP" \
    --font-size 15 \
    --theme monokai \
    --fps-cap 12 \
  --idle-time-limit 0.8 \
  --last-frame-duration 2 \
    --speed 1.15 \
    "$CAST" "$OUT_GIF"
fi

if [[ -n "${PROOF}" && -d "$(dirname "$PROOF")" ]]; then cp -f "$OUT_GIF" "$PROOF"; fi
python3 - "$OUT_GIF" "$CAST" "$PROOF" << 'ENDPY'
import os, sys
gif, cast, proof = sys.argv[1], sys.argv[2], sys.argv[3]
size = os.path.getsize(gif)
print(f"cast bytes={os.path.getsize(cast)}")
print(f"gif bytes={size} ({size/1024/1024:.2f} MiB)  path={gif}")
if size > 3 * 1024 * 1024:
    sys.exit("gif exceeds 3MB")
ENDPY
ls -lh "$OUT_GIF" "$PROOF" "$CAST"
