# CMBS 10-D Knowledge Graph Pipeline

An end-to-end pipeline that scrapes SEC EDGAR for CMBS (Commercial Mortgage-Backed Securities) 10-D distribution reports, cleans the raw HTML into structured markdown, extracts structured data using LLMs, and loads everything into a Neo4j knowledge graph.

## Architecture

```
SEC EDGAR  →  Go Scraper  →  HTML Cleaner  →  LLM Extraction  →  Neo4j
  (10-D)      (scraper/)     (refine/)        (graph/parse)     (graph/load)
```

### 1. Scraper (`scraper/`)

A Go CLI tool that queries the SEC EDGAR full-text search API for CMBS trust filings. It identifies trusts by CIK, discovers 10-D filings, and downloads EX-99.1 exhibit files (the distribution reports) as raw HTML.

### 2. HTML Cleaner (`refine/clean_exhibits.py`)

Parses the raw SEC HTML exhibits—stripping inline styles, font tags, `&nbsp;` spacers, page footers, and other presentation markup—and converts the data tables into clean markdown. This typically achieves 70–90% size reduction while preserving all data content.

### 3. LLM Extraction (`graph/parse.py`)

Sends each cleaned markdown file to an LLM (Minimax M2.5 via OpenRouter) with a detailed system prompt and JSON schema. The model extracts structured data covering:

- **Trust** — name, series, pool balance, loan/property counts, WAC, DSCR
- **Filing** — accession number, distribution/determination dates, total distributions
- **Parties** — servicers, trustees, administrators with contact info
- **Tranches** — class name, CUSIP, pass-through rate, balances, credit support
- **Loans** — property type, location, rates, maturity, balances
- **Loan Snapshots** — per-filing point-in-time data: delinquency, NOI, advances
- **Specially Serviced Loans** — appraisal values, resolution strategies, comments

All extracted data is validated with Pydantic v2 models before loading.

### 4. Neo4j Loader (`graph/load.py`, `graph/schema.py`)

Loads validated extractions into Neo4j using idempotent `MERGE` operations. The graph schema uses:

- **Nodes**: `Trust`, `Filing`, `Party`, `Tranche`, `Loan`, `LoanSnapshot`
- **Relationships**: `REPORTS_ON`, `SERVICES`, `ISSUED`, `CONTAINS_LOAN`, `HAS_SNAPSHOT`, `SNAPSHOT_OF`

Uniqueness constraints and indexes are created automatically on startup.

## Graph Schema

```
(Party)-[:SERVICES]->(Trust)
(Filing)-[:REPORTS_ON]->(Trust)
(Trust)-[:ISSUED]->(Tranche)
(Trust)-[:CONTAINS_LOAN]->(Loan)
(Filing)-[:HAS_SNAPSHOT]->(LoanSnapshot)-[:SNAPSHOT_OF]->(Loan)
```

The `LoanSnapshot` pattern captures temporal data—each filing produces a new snapshot per loan, enabling time-series analysis of delinquency, balance changes, and servicer advances.

## Usage

### Prerequisites

- Python 3.11+
- Go 1.21+ (for the scraper)
- Neo4j 5.x
- OpenRouter API key

### Setup

```bash
pip install -r requirements.txt
```

Set environment variables in `.env`:

```
OPENROUTER_API_KEY=...
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
```

### Run the Pipeline

```bash
# 1. Scrape exhibits from EDGAR (Go)
cd scraper && go run . --download-ex --out-dir exhibits

# 2. Clean HTML to markdown
python3 refine/clean_exhibits.py

# 3. Extract and load into Neo4j
python -m graph.run

# Or dry-run (extract only, save JSON):
python -m graph.run --dry-run

# Process a single file:
python -m graph.run --file TrustName_0000000000-00-000000_ex991.md

# Skip already-loaded filings:
python -m graph.run --skip-existing
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Scraper | Go, SEC EDGAR EFTS API |
| Cleaner | Python, stdlib `html.parser` |
| Extraction | OpenRouter API (Minimax M2.5), Pydantic v2 |
| Graph DB | Neo4j 5.x |
| Retry/Resilience | tenacity, httpx |
