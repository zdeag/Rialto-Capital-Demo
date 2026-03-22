#!/usr/bin/env python3
"""
Cleans SEC CMBS exhibit HTML files from scraper/exhibits/ into structured
markdown tables, stripping all presentation markup (inline styles, font tags,
nbsp spacers, page footers, page breaks) while preserving data content.

Usage:
    python3 refine/clean_exhibits.py                    # process all exhibits
    python3 refine/clean_exhibits.py --file <name.htm>  # process one file
"""

import argparse
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
INPUT_DIR = PROJECT_ROOT / "scraper" / "exhibits"
OUTPUT_DIR = SCRIPT_DIR / "exhibits"


class TableExtractor(HTMLParser):
    """Parses HTML tables into lists of rows/cells with text-only content."""

    def __init__(self):
        super().__init__()
        self.tables = []
        self.current_table = []
        self.current_row = []
        self.current_cell = ""
        self.current_colspan = 1
        self.in_table = False
        self.in_td = False
        self.in_row = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
            self.current_table = []
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag == "td" and self.in_row:
            self.in_td = True
            self.current_cell = ""
            self.current_colspan = 1
            for a, v in attrs:
                if a == "colspan":
                    try:
                        self.current_colspan = int(v)
                    except ValueError:
                        self.current_colspan = 1

    def handle_endtag(self, tag):
        if tag == "td" and self.in_td:
            self.in_td = False
            text = re.sub(r"\s+", " ", self.current_cell).strip()
            self.current_row.append(text)
            for _ in range(self.current_colspan - 1):
                self.current_row.append("")
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.current_table.append(self.current_row)
        elif tag == "table" and self.in_table:
            self.in_table = False
            if self.current_table:
                self.tables.append(self.current_table)

    def handle_data(self, data):
        if self.in_td:
            self.current_cell += data

    def handle_entityref(self, name):
        if self.in_td:
            entity_map = {
                "nbsp": "",
                "copy": "\u00a9",
                "sup1": "\u00b9",
                "amp": "&",
                "lt": "<",
                "gt": ">",
                "quot": '"',
                "ndash": "\u2013",
                "mdash": "\u2014",
            }
            self.current_cell += entity_map.get(name, f"&{name};")

    def handle_charref(self, name):
        if self.in_td:
            try:
                if name.startswith("x"):
                    self.current_cell += chr(int(name[1:], 16))
                else:
                    self.current_cell += chr(int(name))
            except (ValueError, OverflowError):
                self.current_cell += f"&#{name};"


def is_boilerplate(row: list[str]) -> bool:
    text = " ".join(row).lower()
    if "computershare" in text and "rights reserved" in text:
        return True
    if re.search(r"page \d+ of \d+", text):
        return True
    return False


def clean_table(table: list[list[str]]) -> list[list[str]]:
    # Remove all-empty rows
    cleaned = [row for row in table if any(cell.strip() for cell in row)]
    if not cleaned:
        return []

    # Normalize row lengths
    max_cols = max(len(r) for r in cleaned)
    for r in cleaned:
        while len(r) < max_cols:
            r.append("")

    # Remove columns that are entirely empty
    cols_to_keep = []
    for c in range(max_cols):
        if any(row[c].strip() for row in cleaned if c < len(row)):
            cols_to_keep.append(c)

    result = []
    for row in cleaned:
        result.append([row[c] for c in cols_to_keep if c < len(row)])

    return result


def extract_title(html: str) -> str:
    """Pull the trust name and distribution date from the first table."""
    m_trust = re.search(
        r"<font[^>]*>([^<]*(?:Trust|TRUST)[^<]*)</font>", html, re.IGNORECASE
    )
    m_date = re.search(
        r"Distribution\s+Date:[^<]*</font>\s*</p>\s*</td>\s*<td[^>]*>\s*<p[^>]*>"
        r"<font[^>]*>(\d{2}/\d{2}/\d{2})</font>",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    trust = re.sub(r"\s+", " ", m_trust.group(1)).strip() if m_trust else "Unknown Trust"
    date = m_date.group(1) if m_date else "Unknown Date"
    return trust, date


def tables_to_markdown(tables: list[list[list[str]]], trust: str, date: str) -> str:
    lines = []
    lines.append(f"# {trust}")
    lines.append(f"## Distribution Report \u2014 {date}\n")

    table_num = 0
    for table in tables:
        cleaned = clean_table(table)
        cleaned = [r for r in cleaned if not is_boilerplate(r)]
        if not cleaned or len(cleaned) < 2:
            continue

        table_num += 1
        lines.append(f"### Table {table_num}\n")

        for j, row in enumerate(cleaned):
            line = "| " + " | ".join(cell if cell else "" for cell in row) + " |"
            lines.append(line)
            if j == 0:
                lines.append("|" + "|".join(["---"] * len(row)) + "|")

        lines.append("")

    return "\n".join(lines)


def process_file(input_path: Path, output_path: Path) -> dict:
    html = input_path.read_text(encoding="utf-8", errors="replace")
    original_size = len(html)

    parser = TableExtractor()
    parser.feed(html)

    trust, date = extract_title(html)
    markdown = tables_to_markdown(parser.tables, trust, date)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    return {
        "input": input_path.name,
        "output": output_path.name,
        "original_bytes": original_size,
        "cleaned_bytes": len(markdown.encode("utf-8")),
        "tables": len(parser.tables),
    }


def main():
    parser = argparse.ArgumentParser(description="Clean SEC CMBS exhibit HTML to markdown")
    parser.add_argument("--file", type=str, help="Process a single .htm file by name")
    args = parser.parse_args()

    if not INPUT_DIR.exists():
        print(f"Error: input directory not found: {INPUT_DIR}", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.file:
        files = [INPUT_DIR / args.file]
        if not files[0].exists():
            print(f"Error: file not found: {files[0]}", file=sys.stderr)
            sys.exit(1)
    else:
        files = sorted(INPUT_DIR.glob("*.htm"))

    if not files:
        print("No .htm files found in", INPUT_DIR)
        sys.exit(0)

    total_original = 0
    total_cleaned = 0

    for f in files:
        out_name = f.stem + ".md"
        out_path = OUTPUT_DIR / out_name
        result = process_file(f, out_path)
        total_original += result["original_bytes"]
        total_cleaned += result["cleaned_bytes"]
        reduction = 100 * (1 - result["cleaned_bytes"] / result["original_bytes"])
        print(
            f"  {result['input']:<90s} "
            f"{result['original_bytes']:>10,} -> {result['cleaned_bytes']:>8,} "
            f"({reduction:.1f}% reduction, {result['tables']} tables)"
        )

    if len(files) > 1:
        total_reduction = 100 * (1 - total_cleaned / total_original) if total_original else 0
        print(f"\n  Total: {total_original:,} -> {total_cleaned:,} ({total_reduction:.1f}% reduction)")
        print(f"  Processed {len(files)} files -> {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
