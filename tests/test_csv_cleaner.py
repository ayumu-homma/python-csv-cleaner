"""csv_cleaner のユニットテスト。標準ライブラリの unittest のみ使う。"""

from __future__ import annotations

import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import csv_cleaner  # noqa: E402


class ParseDateTests(unittest.TestCase):
    def test_iso_and_slash_and_japanese(self) -> None:
        cases = {
            "2024-01-05": "2024-01-05",
            "2024/1/5": "2024-01-05",
            "2024.07.08": "2024-07-08",
            "2024年3月2日": "2024-03-02",
            "2024/07/08 09:15": "2024-07-08",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                value, ok = csv_cleaner.parse_date(raw)
                self.assertTrue(ok, raw)
                self.assertEqual(value, expected)

    def test_month_day_year(self) -> None:
        value, ok = csv_cleaner.parse_date("05/13/2024")
        self.assertTrue(ok)
        self.assertEqual(value, "2024-05-13")

    def test_day_first_when_month_would_be_invalid(self) -> None:
        value, ok = csv_cleaner.parse_date("13/05/2024")
        self.assertTrue(ok)
        self.assertEqual(value, "2024-05-13")

    def test_unparseable_keeps_original(self) -> None:
        value, ok = csv_cleaner.parse_date("not-a-date")
        self.assertFalse(ok)
        self.assertEqual(value, "not-a-date")

    def test_blank_stays_blank(self) -> None:
        value, ok = csv_cleaner.parse_date("   ")
        self.assertTrue(ok)
        self.assertEqual(value.strip(), "")


class DuplicateTests(unittest.TestCase):
    def test_keep_first(self) -> None:
        rows = [
            {"id": "A-001", "name": "first"},
            {"id": "A-002", "name": "two"},
            {"id": "A-001", "name": "second"},
        ]
        out = csv_cleaner.drop_duplicates(rows, "id", "first")
        self.assertEqual([r["name"] for r in out], ["first", "two"])

    def test_keep_last(self) -> None:
        rows = [
            {"id": "A-001", "name": "first"},
            {"id": "A-002", "name": "two"},
            {"id": "A-001", "name": "second"},
        ]
        out = csv_cleaner.drop_duplicates(rows, "id", "last")
        self.assertEqual([r["name"] for r in out], ["two", "second"])


class SampleFileTests(unittest.TestCase):
    """README と同じコマンドで、samples/output.csv と一致することを確認する。"""

    def test_sample_input_matches_committed_output(self) -> None:
        input_path = ROOT / "samples" / "input.csv"
        expected_path = ROOT / "samples" / "output.csv"
        self.assertTrue(input_path.is_file())
        self.assertTrue(expected_path.is_file(), "先に samples/output.csv を生成してください")

        with tempfile.TemporaryDirectory() as tmp:
            actual_path = Path(tmp) / "clean.csv"
            code = csv_cleaner.run(
                [
                    "--input",
                    str(input_path),
                    "--output",
                    str(actual_path),
                    "--key",
                    "id",
                    "--date-col",
                    "date",
                    "--columns",
                    "id,name,date,category,note",
                    "--keep",
                    "first",
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                _read_rows(actual_path),
                _read_rows(expected_path),
            )

    def test_unparseable_date_warns_and_keeps_value(self) -> None:
        input_path = ROOT / "samples" / "input.csv"
        with tempfile.TemporaryDirectory() as tmp:
            actual_path = Path(tmp) / "clean.csv"
            buf = io.StringIO()
            old = sys.stderr
            sys.stderr = buf
            try:
                code = csv_cleaner.run(
                    [
                        "--input",
                        str(input_path),
                        "--output",
                        str(actual_path),
                        "--key",
                        "id",
                        "--date-col",
                        "date",
                        "--columns",
                        "id,name,date,category,note",
                    ]
                )
            finally:
                sys.stderr = old
            self.assertEqual(code, 0)
            err = buf.getvalue()
            self.assertIn("not-a-date", err)
            rows = _read_rows(actual_path)
            notebook = [r for r in rows if r["id"] == "A-004"][0]
            self.assertEqual(notebook["date"], "not-a-date")
            # 重複 A-001 は先の行だけ
            self.assertEqual(sum(1 for r in rows if r["id"] == "A-001"), 1)
            self.assertEqual(
                [r["id"] for r in rows],
                ["A-001", "A-002", "A-003", "A-004", "A-005"],
            )


class CliErrorTests(unittest.TestCase):
    def test_missing_input_returns_1(self) -> None:
        code = csv_cleaner.run(
            ["--input", "/tmp/does-not-exist-csv-cleaner.csv", "--output", "/tmp/x.csv"]
        )
        self.assertEqual(code, 1)

    def test_missing_key_column_returns_1(self) -> None:
        input_path = ROOT / "samples" / "input.csv"
        with tempfile.TemporaryDirectory() as tmp:
            code = csv_cleaner.run(
                [
                    "--input",
                    str(input_path),
                    "--output",
                    str(Path(tmp) / "x.csv"),
                    "--key",
                    "no_such_column",
                ]
            )
        self.assertEqual(code, 1)


def _read_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


if __name__ == "__main__":
    unittest.main()
