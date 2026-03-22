"""Neo4j constraints and indexes for the CMBS knowledge graph.

All constraints use IF NOT EXISTS so setup_schema() is idempotent.
"""

from neo4j import Driver

CONSTRAINTS = [
    # Trust — unique on name
    (
        "CREATE CONSTRAINT trust_name IF NOT EXISTS "
        "FOR (t:Trust) REQUIRE t.name IS UNIQUE"
    ),
    # Filing — unique on accessionNumber
    (
        "CREATE CONSTRAINT filing_accession IF NOT EXISTS "
        "FOR (f:Filing) REQUIRE f.accessionNumber IS UNIQUE"
    ),
    # Party — composite unique on (name, role)
    (
        "CREATE CONSTRAINT party_name_role IF NOT EXISTS "
        "FOR (p:Party) REQUIRE (p.name, p.role) IS UNIQUE"
    ),
    # Tranche — unique on cusip
    (
        "CREATE CONSTRAINT tranche_cusip IF NOT EXISTS "
        "FOR (tr:Tranche) REQUIRE tr.cusip IS UNIQUE"
    ),
    # Loan — composite unique on (prosId, trustName)
    (
        "CREATE CONSTRAINT loan_prosid_trust IF NOT EXISTS "
        "FOR (l:Loan) REQUIRE (l.prosId, l.trustName) IS UNIQUE"
    ),
    # LoanSnapshot — composite unique on (accessionNumber, prosId)
    (
        "CREATE CONSTRAINT snapshot_accession_prosid IF NOT EXISTS "
        "FOR (s:LoanSnapshot) REQUIRE (s.accessionNumber, s.prosId) IS UNIQUE"
    ),
]

INDEXES = [
    (
        "CREATE INDEX loan_property_type IF NOT EXISTS "
        "FOR (l:Loan) ON (l.propertyType)"
    ),
    "CREATE INDEX loan_state IF NOT EXISTS FOR (l:Loan) ON (l.state)",
    (
        "CREATE INDEX snapshot_delinquency IF NOT EXISTS "
        "FOR (s:LoanSnapshot) ON (s.monthsDelinquent)"
    ),
    "CREATE INDEX party_name IF NOT EXISTS FOR (p:Party) ON (p.name)",
]


def setup_schema(driver: Driver, database: str | None = None) -> None:
    """Create all constraints and indexes. Safe to call repeatedly."""
    with driver.session(database=database) as session:
        for stmt in CONSTRAINTS + INDEXES:
            session.run(stmt)
    print(f"  Schema ready: {len(CONSTRAINTS)} constraints, {len(INDEXES)} indexes")
