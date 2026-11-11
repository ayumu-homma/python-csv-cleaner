#!/usr/bin/env bash
# asciinema で録画する公開サンプル用の短い実演。ダミーデータのみ。
set -euo pipefail
cd "$(dirname "$0")/.."
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export PYTHONUNBUFFERED=1



cat() {
  if [[ "${1:-}" == *.csv ]]; then
    preview_csv "$1"
  else
    command cat "$@"
  fi
}

preview_csv() {
  python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text(encoding="utf-8-sig"), end="")' "$1"
}

type_run() {
  local cmd="$1"
  local prompt="${2:-$ }"
  printf '%s' "$prompt"
  sleep 0.25
  local i
  for ((i=0; i<${#cmd}; i++)); do
    printf '%s' "${cmd:$i:1}"
    sleep 0.018
  done
  printf '\n'
  sleep 0.25
  eval "$cmd"
}

export TERM="${TERM:-xterm-256color}"
clear || true
echo "python-csv-cleaner  公開サンプル（ダミーデータ）"
echo "日付のばらつきと重複を除いて、すぐ使える CSV にします。"
echo
sleep 0.6

echo "===== 整理前 ====="
sleep 0.2
type_run "cat samples/input.csv"
echo
sleep 1.2

echo "===== 整理する ====="
type_run "python3 src/csv_cleaner.py --input samples/input.csv --output /tmp/cleaned-demo.csv --key id --date-col date --columns id,name,date,category,note"
echo
sleep 0.8

echo "===== 整理後 ====="
type_run "cat /tmp/cleaned-demo.csv"
echo
sleep 1.0

echo "===== テスト ====="
type_run "python3 -m unittest discover -s tests 2>&1 | tail -5"
echo
sleep 1.5
echo "完了。整理後のファイルとテスト結果を公開サンプルとして確認できます。"
sleep 1.2
