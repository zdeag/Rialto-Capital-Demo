---
name: sync-10d
description: Sync a 10-D filing into the Neo4j knowledge graph by accession number. Use when the user wants to ingest, sync, or load a specific SEC 10-D filing.
argument-hint: [accession-number]
---

Sync a 10-D filing into the CMBS knowledge graph. The user provides an SEC accession number (e.g. `0001628297-26-000127`).

## Pipeline Overview

The full pipeline is: **EDGAR fetch → HTML clean → LLM extract → Neo4j load**

## Step 1: Resolve the filing on EDGAR

```
curl -s -H "User-Agent: RialtoCapital research@example.com" \
  "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&accession=$ARGUMENTS&type=10-D&output=atom"
```

You need to extract:
- **CIK** (numeric, strip leading zeros for URL paths)
- **Trust name** (the entity/filer name)
- **ADSH** (the accession number with dashes: `XXXXXXXXXX-XX-XXXXXX`)

## Step 2: Download the EX-99.1 exhibit

Construct the filing index URL and find the EX-99.1:

```
# Convert ADSH to path format (remove dashes)
ADSH_PATH=$(echo "$ADSH" | tr -d '-')
INDEX_URL="https://www.sec.gov/Archives/edgar/data/${CIK}/${ADSH_PATH}/${ADSH}-index.html"
```

Fetch the index HTML, find the EX-99.1 document URL, then download it:

```
# Save to scraper/exhibits/ with the naming convention: TrustName_AccessionNumber_ex991.htm
# Replace spaces with underscores, remove commas/periods from trust name
```

The filename MUST follow this pattern: `{TrustName}_{AccessionNumber}_ex991.htm`
- Spaces → underscores
- Remove commas and periods from trust name

## Step 3: Clean HTML to markdown

Run the Python cleaning script on just the new file:

```bash
cd /Users/zacharydeaguuar/Documents/Rialto_Capital
python3 refine/clean_exhibits.py --file "{filename}.htm"
```

This outputs a `.md` file to `refine/exhibits/`.

Verify the output file exists and has reasonable content (should be >50 chars, contain markdown tables).

## Step 4: Extract and load into Neo4j

Run the graph pipeline on just the cleaned file:

```bash
cd /Users/zacharydeaguuar/Documents/Rialto_Capital
python3 -m graph.run --file "{filename}.md" --skip-existing
```

This will:
1. Send the markdown to the LLM (OpenRouter/Kimi) for structured extraction
2. Validate with Pydantic models
3. MERGE all entities into Neo4j (Trust, Filing, Parties, Tranches, Loans, Snapshots, Specially Serviced)

## Step 5: Verify in Neo4j

After loading, query Neo4j via MCP to confirm the filing was loaded:

```cypher
MATCH (f:Filing {accessionNumber: $accession})-[:REPORTS_ON]->(t:Trust)
OPTIONAL MATCH (t)-[:CONTAINS_LOAN]->(l:Loan)
RETURN t.name AS Trust, f.distributionDate AS DistributionDate,
       count(l) AS Loans, f.totalDistributed AS TotalDistributed
```

Report the results to the user: trust name, distribution date, loan count, and total distributed.

## Error Handling

- If the accession number is not found on EDGAR, tell the user and suggest they verify the number.
- If EX-99.1 is not found in the filing index, the filing may not have a distribution report exhibit.
- If the cleaning step produces an empty/tiny file, the HTML may not contain parseable tables.
- If `--skip-existing` causes it to skip, inform the user the filing is already in the graph and ask if they want to re-process (remove the flag to overwrite).
- If the LLM extraction fails, check `graph/errors/` for the saved raw response.

## Environment Requirements

These environment variables must be set (from `.env`):
- `OPENROUTER_API_KEY` — for LLM extraction
- `NEO4J_URI` — Neo4j connection
- `NEO4J_USERNAME` / `NEO4J_PASSWORD` — Neo4j auth
- `NEO4J_DATABASE` (optional)
