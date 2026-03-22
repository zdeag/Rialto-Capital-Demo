#!/usr/bin/env python3
"""CLI orchestrator for the CMBS 10-D → Neo4j knowledge graph pipeline.

Usage:
    python -m graph.run                       # process all 113 files
    python -m graph.run --file <name.md>      # process one file
    python -m graph.run --dry-run             # extract JSON only, no Neo4j
    python -m graph.run --skip-existing       # skip already-loaded filings
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from graph.parse import ExtractionError, extract_filing

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
EXHIBITS_DIR = PROJECT_ROOT / "refine" / "exhibits"

# Load .env from project root
load_dotenv(PROJECT_ROOT / ".env")

# Filename pattern: TrustName_AccessionNumber_ex991.md
FILENAME_RE = re.compile(r"^(.+?)_(\d{10}-\d{2}-\d{6})_ex991\.md$")


def parse_filename(name: str) -> tuple[str, str]:
    """Extract trust_name and accession_number from an exhibit filename.

    Returns (trust_name_with_spaces, accession_number).
    """
    m = FILENAME_RE.match(name)
    if not m:
        raise ValueError(f"Filename doesn't match expected pattern: {name}")
    raw_trust = m.group(1)
    accession = m.group(2)
    # Convert underscores back to spaces for the trust name
    trust_name = raw_trust.replace("_", " ")
    return trust_name, accession


def filing_exists(driver, accession_number: str, database: str | None = None) -> bool:
    """Check if a Filing node with this accession number already exists."""
    with driver.session(database=database) as session:
        result = session.run(
            "MATCH (f:Filing {accessionNumber: $acc}) RETURN count(f) AS cnt",
            acc=accession_number,
        )
        return result.single()["cnt"] > 0


def main():
    parser = argparse.ArgumentParser(
        description="CMBS 10-D → Neo4j knowledge graph pipeline"
    )
    parser.add_argument("--file", type=str, help="Process a single .md file by name")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract JSON only, don't load into Neo4j",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip filings already loaded into Neo4j",
    )
    args = parser.parse_args()

    # Validate env vars
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("Error: OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    driver = None
    if not args.dry_run:
        if not os.environ.get("NEO4J_URI"):
            print("Error: NEO4J_URI not set", file=sys.stderr)
            sys.exit(1)

        from neo4j import GraphDatabase

        from graph.schema import setup_schema

        neo4j_uri = os.environ["NEO4J_URI"]
        neo4j_user = os.environ.get("NEO4J_USERNAME", "neo4j")
        neo4j_password = os.environ.get("NEO4J_PASSWORD", "")
        neo4j_database = os.environ.get("NEO4J_DATABASE")

        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        driver.verify_connectivity()
        print(f"Connected to Neo4j ({neo4j_uri})")
        setup_schema(driver, database=neo4j_database)

    # Collect files
    if not EXHIBITS_DIR.exists():
        print(f"Error: exhibits directory not found: {EXHIBITS_DIR}", file=sys.stderr)
        sys.exit(1)

    if args.file:
        files = [EXHIBITS_DIR / args.file]
        if not files[0].exists():
            print(f"Error: file not found: {files[0]}", file=sys.stderr)
            sys.exit(1)
    else:
        files = sorted(EXHIBITS_DIR.glob("*.md"))

    if not files:
        print("No .md files found in", EXHIBITS_DIR)
        sys.exit(0)

    print(f"\nProcessing {len(files)} files...\n")

    processed = 0
    failed = 0
    skipped = 0

    for i, filepath in enumerate(files, 1):
        try:
            trust_name, accession_number = parse_filename(filepath.name)
        except ValueError as e:
            print(f"  [{i}/{len(files)}] SKIP {filepath.name} — {e}")
            skipped += 1
            continue

        # Skip if content is too short
        content = filepath.read_text(encoding="utf-8")
        if len(content.strip()) < 50:
            print(f"  [{i}/{len(files)}] SKIP {filepath.name} — empty/too short")
            skipped += 1
            continue

        # Skip existing
        if args.skip_existing and driver and filing_exists(driver, accession_number, neo4j_database):
            print(f"  [{i}/{len(files)}] SKIP {trust_name} — already loaded")
            skipped += 1
            continue

        # Extract
        print(f"  [{i}/{len(files)}] {trust_name}", flush=True)
        file_t0 = time.time()
        try:
            extraction = extract_filing(trust_name, accession_number, content)
        except ExtractionError as e:
            print(f"    ↳ FAILED: {e}")
            failed += 1
            continue

        # Load or dry-run
        if args.dry_run:
            out_path = SCRIPT_DIR / "dry_run" / f"{accession_number}.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                extraction.model_dump_json(indent=2, by_alias=True),
                encoding="utf-8",
            )
            elapsed = time.time() - file_t0
            print(
                f"    ↳ Done in {elapsed:.1f}s — "
                f"dry-run saved to {out_path.name}",
                flush=True,
            )
        else:
            from graph.load import load_filing

            print("    ↳ Loading into Neo4j...", flush=True)
            summary = load_filing(driver, extraction, database=neo4j_database)
            elapsed = time.time() - file_t0
            print(
                f"    ↳ Done in {elapsed:.1f}s — "
                f"loaded {summary['loans']} loans, "
                f"{summary['specially_serviced']} specially serviced",
                flush=True,
            )

        processed += 1

        # Rate limit: ~2s between API calls
        if i < len(files):
            time.sleep(2)

    # Summary
    print(f"\nDone: {processed} processed, {failed} failed, {skipped} skipped")

    if driver:
        driver.close()


if __name__ == "__main__":
    main()
