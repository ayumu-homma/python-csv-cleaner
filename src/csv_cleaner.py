#!/usr/bin/env python3
"""手元の CSV を整理する、小さなコマンドラインツール。

公開用のサンプルであり、受注成果物ではありません。
標準ライブラリのみを使います。
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

# 終了コード: 成功 0、入力や引数の不備 1、予期しないエラー 2
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_ERROR = 2

# 年が先頭の形式を先に試す。Ambiguous な 01/02/2024 は README のとおり月/日/年。
_DATE_FORMATS_YEAR_FIRST = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y.%m.%d %H:%M:%S",
)

_JA_DATE = re.compile(
    r"^\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*$"
)

_YMD_NUMERIC = re.compile(
    r"^\s*(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})"
    r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*$"
)

_MDY_OR_DMY = re.compile(
    r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})"
    r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*$"
)


class CsvCleanerError(Exception):
    """入力や引数が使えないときの例外。終了コード 1 にする。"""


def parse_date(value: str) -> tuple[str, bool]:
    """日付文字列を YYYY-MM-DD にそろえる。

    戻り値は (結果の文字列, 変換できたか)。
    空欄はそのまま返す。変換できない値は警告したうえで元の値を残す。
    """
    raw = value.strip()
    if raw == "":
        return value, True

    m = _JA_DATE.match(raw)
    if m:
        dt = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if dt:
            return dt.isoformat(), True

    m = _YMD_NUMERIC.match(raw)
    if m:
        dt = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if dt:
            return dt.isoformat(), True

    for fmt in _DATE_FORMATS_YEAR_FIRST:
        dt = _try_strptime(raw, fmt)
        if dt:
            return dt.date().isoformat(), True

    m = _MDY_OR_DMY.match(raw)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        # 13以上は日とみなし、日/月/年
        if a > 12 and 1 <= b <= 12:
            dt = _safe_date(y, b, a)
            if dt:
                return dt.isoformat(), True
        # それ以外は月/日/年（このツールの方針）
        dt = _safe_date(y, a, b)
        if dt:
            return dt.isoformat(), True
        # 月/日で無効なら日/月を再試行
        dt = _safe_date(y, b, a)
        if dt:
            return dt.isoformat(), True

    return value, False


def _try_strptime(raw: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(raw, fmt)
    except ValueError:
        return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def read_rows(path: Path, encoding: str) -> tuple[list[str], list[dict[str, str]]]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CsvCleanerError(f"入力ファイルを読めません: {path} ({exc})") from exc

    if not data:
        raise CsvCleanerError(f"入力ファイルが空です: {path}")

    text = data.decode(encoding)
    # utf-8-sig で開いた場合は BOM は既に除かれる。utf-8 指定でも先頭 BOM を除く。
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise CsvCleanerError("ヘッダー行（1行目の列名）がありません。")

    headers = [_strip_header(h) for h in reader.fieldnames]
    if any(h == "" for h in headers):
        raise CsvCleanerError("ヘッダーに空の列名があります。")
    if len(headers) != len(set(headers)):
        raise CsvCleanerError("ヘッダーの列名が重複しています: " + ", ".join(headers))

    rows: list[dict[str, str]] = []
    for raw in reader:
        # 空行（全欄が空）は捨てる
        stripped = {_strip_header(k): (v or "").strip() for k, v in raw.items()}
        if not any(stripped.values()):
            continue
        rows.append(stripped)
    return headers, rows


def _strip_header(name: str | None) -> str:
    return (name or "").replace("\ufeff", "").strip()


def drop_duplicates(
    rows: list[dict[str, str]], key: str, keep: str
) -> list[dict[str, str]]:
    if keep not in {"first", "last"}:
        raise CsvCleanerError("--keep は first または last を指定してください。")

    seen: dict[str, int] = {}
    kept: list[dict[str, str]] = []

    if keep == "first":
        for row in rows:
            k = row.get(key, "")
            if k in seen:
                continue
            seen[k] = 1
            kept.append(row)
        return kept

    # last: 後ろから見て、あとで元の出現順を保つ
    for row in reversed(rows):
        k = row.get(key, "")
        if k in seen:
            continue
        seen[k] = 1
        kept.append(row)
    kept.reverse()
    return kept


def normalize_dates(
    rows: list[dict[str, str]], date_cols: list[str]
) -> list[str]:
    warnings_out: list[str] = []
    for i, row in enumerate(rows, start=1):
        for col in date_cols:
            original = row.get(col, "")
            converted, ok = parse_date(original)
            if not ok:
                warnings_out.append(
                    f"ヘッダーを除く{i}行目の列 '{col}' を日付にできませんでした。"
                    f"元の値を残します: {original!r}"
                )
            row[col] = converted
    return warnings_out


def select_columns(
    rows: list[dict[str, str]],
    source_headers: list[str],
    columns: list[str] | None,
) -> tuple[list[str], list[dict[str, str]]]:
    if not columns:
        return source_headers, rows

    missing = [c for c in columns if c not in source_headers]
    if missing:
        raise CsvCleanerError(
            "指定した列が入力にありません: " + ", ".join(missing)
        )
    out = [{c: row.get(c, "") for c in columns} for row in rows]
    return columns, out


def write_csv(
    path: Path,
    headers: list[str],
    rows: list[dict[str, str]],
    encoding: str,
    with_bom: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload_encoding = encoding
    # utf-8-sig は書き込み時に BOM が付く。--no-bom のときは utf-8 で書く。
    if encoding.lower() in {"utf-8", "utf8", "utf-8-sig"}:
        payload_encoding = "utf-8-sig" if with_bom else "utf-8"
    try:
        with path.open("w", encoding=payload_encoding, newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=headers,
                lineterminator="\n",
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({h: row.get(h, "") for h in headers})
    except OSError as exc:
        raise CsvCleanerError(f"出力ファイルを書けません: {path} ({exc})") from exc


def parse_columns(value: str | None) -> list[str] | None:
    if value is None or value.strip() == "":
        return None
    cols = [c.strip() for c in value.split(",") if c.strip()]
    if not cols:
        return None
    return cols


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csv_cleaner",
        description="CSV の重複削除・列の抽出・日付形式のそろえを行います（公開サンプル）。",
    )
    parser.add_argument("--input", "-i", required=True, help="入力 CSV のパス")
    parser.add_argument("--output", "-o", required=True, help="出力 CSV のパス")
    parser.add_argument(
        "--key",
        help="重複とみなす列名。指定しない場合は重複削除をしない",
    )
    parser.add_argument(
        "--keep",
        choices=("first", "last"),
        default="first",
        help="重複時に残す行（既定: first = 先に出てきた行）",
    )
    parser.add_argument(
        "--date-col",
        action="append",
        default=[],
        dest="date_cols",
        help="日付を YYYY-MM-DD にそろえる列名。複数回指定できる",
    )
    parser.add_argument(
        "--columns",
        help="残す列をカンマ区切りで指定する（この順で出力する）",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        help="入力の文字コード（既定: utf-8-sig。BOM 付き UTF-8 も読める）",
    )
    parser.add_argument(
        "--no-bom",
        action="store_true",
        help="出力を BOM なし UTF-8 にする（既定は Excel 向けに BOM 付き）",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return EXIT_USAGE if code not in (0, None) else EXIT_OK

    try:
        in_path = Path(args.input)
        out_path = Path(args.output)
        if not in_path.is_file():
            raise CsvCleanerError(f"入力ファイルがありません: {in_path}")

        headers, rows = read_rows(in_path, args.encoding)

        date_cols = args.date_cols or []
        missing_dates = [c for c in date_cols if c not in headers]
        if missing_dates:
            raise CsvCleanerError(
                "--date-col の列が入力にありません: " + ", ".join(missing_dates)
            )
        for msg in normalize_dates(rows, date_cols):
            print(msg, file=sys.stderr)

        if args.key:
            if args.key not in headers:
                raise CsvCleanerError(f"--key の列が入力にありません: {args.key}")
            rows = drop_duplicates(rows, args.key, args.keep)

        columns = parse_columns(args.columns)
        headers, rows = select_columns(rows, headers, columns)

        write_csv(
            out_path,
            headers,
            rows,
            args.encoding,
            with_bom=not args.no_bom,
        )
        print(f"wrote {len(rows)} rows to {out_path}", file=sys.stderr)
        return EXIT_OK
    except CsvCleanerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 — CLI の最終防波堤
        print(f"unexpected error: {exc}", file=sys.stderr)
        return EXIT_ERROR


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
