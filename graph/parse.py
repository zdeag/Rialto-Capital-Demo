"""OpenRouter/Kimi extraction: sends full MD file and returns FilingExtraction.

Single API call per file — cross-table references (Pros IDs across Loan Detail,
Delinquency, and Specially Serviced) require full context.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from graph.models import FilingExtraction

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "minimax/minimax-m2.5"
ERRORS_DIR = Path(__file__).resolve().parent / "errors"

SYSTEM_PROMPT = """\
You are a CMBS (Commercial Mortgage-Backed Securities) data extraction specialist.
Given a 10-D distribution report in markdown table format, extract structured data
into the exact JSON schema below.

## Output JSON Schema

Return a single JSON object (no markdown fencing, no commentary) with these keys:

{
  "trust": {
    "name": "string — full trust name",
    "series": "string | null — series identifier (e.g. '2017-C1')",
    "originalBalance": "float | null — original pool balance",
    "currentBalance": "float | null — current pool balance",
    "loanCount": "int | null — number of mortgage loans",
    "propertyCount": "int | null — number of properties",
    "wac": "float | null — weighted average coupon",
    "weightedAvgDscr": "float | null — weighted average DSCR"
  },
  "filing": {
    "accessionNumber": "PROVIDED BY USER — do NOT extract",
    "distributionDate": "string | null — MM/DD/YY format",
    "determinationDate": "string | null — MM/DD/YY format",
    "totalInterest": "float | null — total interest distributed",
    "totalPrincipal": "float | null — total principal distributed",
    "totalDistributed": "float | null — total distribution amount"
  },
  "parties": [
    {
      "name": "string — organization name",
      "role": "string — one of: Depositor, Master Servicer, Special Servicer, Trustee, Certificate Administrator, Operating Advisor, Asset Representations Reviewer",
      "city": "string | null",
      "state": "string | null — 2-letter code",
      "phone": "string | null",
      "email": "string | null"
    }
  ],
  "tranches": [
    {
      "className": "string — e.g. 'A-1', 'X-A'",
      "cusip": "string | null — 9-character CUSIP",
      "passThroughRate": "float | null — as percentage, e.g. 3.189",
      "originalBalance": "float | null",
      "endingBalance": "float | null",
      "currentCreditSupport": "float | null — as percentage",
      "originalCreditSupport": "float | null — as percentage"
    }
  ],
  "loans": [
    {
      "prosId": "string — the loan identifier (Pros ID, OMCR, or similar)",
      "loanId": "string | null — secondary loan name/ID",
      "propertyType": "string | null — e.g. Office, Retail, Multifamily",
      "city": "string | null",
      "state": "string | null — 2-letter code",
      "grossRate": "float | null — mortgage rate as percentage",
      "interestAccrualType": "string | null — e.g. 30/360, Actual/360",
      "maturityDate": "string | null",
      "anticipatedRepayDate": "string | null",
      "originalBalance": "float | null",
      "endingBalance": "float | null",
      "isInterestOnly": "boolean | null"
    }
  ],
  "loanSnapshots": [
    {
      "prosId": "string — FK matching loans[].prosId",
      "endingBalance": "float | null",
      "scheduledInterest": "float | null",
      "scheduledPrincipal": "float | null",
      "paidThroughDate": "string | null",
      "monthsDelinquent": "int | null — 0 if current",
      "mortgageLoanStatus": "string | null — e.g. Current, 30 Days, 60 Days, Foreclosure, REO",
      "outstandingPiAdvances": "float | null",
      "actualBalance": "float | null — actual/total balance including advances",
      "mostRecentNoi": "float | null — most recent Net Operating Income"
    }
  ],
  "speciallyServiced": [
    {
      "prosId": "string — FK matching loans[].prosId",
      "loanId": "string | null",
      "appraisalValue": "float | null",
      "appraisalDate": "string | null",
      "noi": "float | null",
      "dscr": "float | null",
      "servicingTransferDate": "string | null",
      "resolutionStrategyCode": "string | null",
      "specialServicingComments": "string | null — full text of comments"
    }
  ]
}

## Extraction Rules

1. **Numbers**: Strip commas, dollar signs ($), percent signs (%).
   "--", "N/A", "n/a", blank cells = null.
2. **Rates/percentages**: Store as-is (e.g. 3.189 not 0.03189).
3. **Dates**: Preserve original format from the filing.
4. **accessionNumber**: Use EXACTLY the value provided by the user. Never extract it.
5. **prosId consistency**: The same loan's Pros ID must match across loans, loanSnapshots,
   and speciallyServiced arrays.
6. **Parties**: Extract from "Table of Contents / Contacts" section OR
   "TRANSACTION PARTIES" section. Combine role + name + contact details.
7. **Tranches**: From "Certificate Distribution Detail" tables. Skip subtotal/total rows.
8. **Loans**: From "Mortgage Loan Detail" tables (Parts 1 & 2).
9. **LoanSnapshots**: Combine data from Mortgage Loan Detail Parts 1 & 2 AND
   Delinquency Loan Detail. One snapshot per loan.
10. **Specially Serviced**: From "Specially Serviced Loan Detail" Parts 1 & 2.
    If no specially serviced section exists, return empty array.
11. Return ONLY the JSON object. No explanation, no markdown fencing.
"""


USER_PROMPT_TEMPLATE = """\
Trust name: {trust_name}
Accession number: {accession_number}

Extract all structured data from the following 10-D distribution report.
Use the accession number exactly as provided above for filing.accessionNumber.

---

{content}
"""


class ExtractionError(Exception):
    """Raised when extraction fails after retries."""


def _get_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("Error: OPENROUTER_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)
    return key


def _log_retry(retry_state):
    print(
        f"    ↳ Retry {retry_state.attempt_number}/3 "
        f"after {retry_state.outcome.exception().__class__.__name__}: "
        f"{retry_state.outcome.exception()}",
        flush=True,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=4, min=4, max=16),
    retry=retry_if_exception_type((httpx.HTTPError, json.JSONDecodeError, KeyError)),
    before_sleep=_log_retry,
    reraise=True,
)
def _call_openrouter(trust_name: str, accession_number: str, content: str) -> dict:
    """Send MD content to Kimi via OpenRouter, return parsed JSON dict."""
    api_key = _get_api_key()

    user_prompt = USER_PROMPT_TEMPLATE.format(
        trust_name=trust_name,
        accession_number=accession_number,
        content=content,
    )

    input_chars = len(SYSTEM_PROMPT) + len(user_prompt)
    est_tokens = input_chars // 4
    print(f"    ↳ Sending ~{est_tokens:,} tokens to {MODEL}...", flush=True)

    payload = {
        "model": MODEL,
        "temperature": 0.0,
        "max_tokens": 16384,
        "provider": {
            "order": ["SambaNova"],
            "allow_fallbacks": True,
        },
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    t0 = time.time()
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
    elapsed = time.time() - t0

    result = resp.json()
    raw_text = result["choices"][0]["message"]["content"]

    # Log usage if available
    usage = result.get("usage", {})
    prompt_tok = usage.get("prompt_tokens", "?")
    completion_tok = usage.get("completion_tokens", "?")
    print(
        f"    ↳ Response in {elapsed:.1f}s "
        f"({prompt_tok} in / {completion_tok} out tokens)",
        flush=True,
    )

    # Strip markdown fencing if model wraps it
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]  # drop opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)

    return json.loads(cleaned)


def extract_filing(
    trust_name: str,
    accession_number: str,
    content: str,
) -> FilingExtraction:
    """Extract structured data from an MD file's content.

    Args:
        trust_name: Trust name parsed from filename.
        accession_number: SEC accession number parsed from filename.
        content: Full markdown content of the 10-D exhibit.

    Returns:
        Validated FilingExtraction model.

    Raises:
        ExtractionError: If extraction or validation fails.
    """
    if len(content.strip()) < 50:
        raise ExtractionError(f"Content too short ({len(content)} chars), skipping")

    print(f"    ↳ Extracting from {len(content):,} chars of markdown...", flush=True)

    try:
        raw = _call_openrouter(trust_name, accession_number, content)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        raise ExtractionError(f"API call failed after retries: {e}") from e

    # Force accession_number from filename, never trust LLM
    if "filing" not in raw:
        raw["filing"] = {}
    raw["filing"]["accessionNumber"] = accession_number

    print("    ↳ Validating with Pydantic...", flush=True)
    try:
        result = FilingExtraction.model_validate(raw)
        print(
            f"    ↳ Validated: {len(result.loans)} loans, "
            f"{len(result.tranches)} tranches, "
            f"{len(result.loan_snapshots)} snapshots, "
            f"{len(result.specially_serviced)} specially serviced",
            flush=True,
        )
        return result
    except ValidationError as e:
        # Save failed extraction for manual review
        ERRORS_DIR.mkdir(parents=True, exist_ok=True)
        error_path = ERRORS_DIR / f"{accession_number}.json"
        error_path.write_text(
            json.dumps({"raw_response": raw, "error": str(e)}, indent=2),
            encoding="utf-8",
        )
        raise ExtractionError(
            f"Pydantic validation failed (saved to {error_path}): {e}"
        ) from e
