"""Neo4j MERGE-based loading for CMBS knowledge graph.

Every node uses MERGE on its uniqueness key with ON CREATE SET / ON MATCH SET
for idempotent loading. Batch operations use UNWIND for performance.
"""

from __future__ import annotations

from neo4j import Driver

from graph.models import FilingExtraction


def load_filing(driver: Driver, extraction: FilingExtraction, database: str | None = None) -> dict:
    """Load a single FilingExtraction into Neo4j.

    Returns a summary dict with counts of entities loaded.
    """
    trust_name = extraction.trust.name
    accession = extraction.filing.accession_number

    with driver.session(database=database) as session:
        # 1. Trust
        session.run(
            """
            MERGE (t:Trust {name: $name})
            ON CREATE SET
                t.series = $series,
                t.originalBalance = $originalBalance,
                t.currentBalance = $currentBalance,
                t.loanCount = $loanCount,
                t.propertyCount = $propertyCount,
                t.wac = $wac,
                t.weightedAvgDscr = $weightedAvgDscr
            ON MATCH SET
                t.currentBalance = COALESCE($currentBalance, t.currentBalance),
                t.loanCount = COALESCE($loanCount, t.loanCount),
                t.propertyCount = COALESCE($propertyCount, t.propertyCount),
                t.wac = COALESCE($wac, t.wac),
                t.weightedAvgDscr = COALESCE($weightedAvgDscr, t.weightedAvgDscr)
            """,
            name=trust_name,
            series=extraction.trust.series,
            originalBalance=extraction.trust.original_balance,
            currentBalance=extraction.trust.current_balance,
            loanCount=extraction.trust.loan_count,
            propertyCount=extraction.trust.property_count,
            wac=extraction.trust.wac,
            weightedAvgDscr=extraction.trust.weighted_avg_dscr,
        )

        # 2. Filing → REPORTS_ON → Trust
        session.run(
            """
            MERGE (f:Filing {accessionNumber: $accession})
            ON CREATE SET
                f.distributionDate = $distributionDate,
                f.determinationDate = $determinationDate,
                f.totalInterest = $totalInterest,
                f.totalPrincipal = $totalPrincipal,
                f.totalDistributed = $totalDistributed
            WITH f
            MATCH (t:Trust {name: $trustName})
            MERGE (f)-[:REPORTS_ON]->(t)
            """,
            accession=accession,
            distributionDate=extraction.filing.distribution_date,
            determinationDate=extraction.filing.determination_date,
            totalInterest=extraction.filing.total_interest,
            totalPrincipal=extraction.filing.total_principal,
            totalDistributed=extraction.filing.total_distributed,
            trustName=trust_name,
        )

        # 3. Parties → SERVICES → Trust
        if extraction.parties:
            parties_data = [
                {
                    "name": p.name,
                    "role": p.role,
                    "city": p.city,
                    "state": p.state,
                    "phone": p.phone,
                    "email": p.email,
                }
                for p in extraction.parties
            ]
            session.run(
                """
                UNWIND $parties AS party
                MERGE (p:Party {name: party.name, role: party.role})
                ON CREATE SET
                    p.city = party.city,
                    p.state = party.state,
                    p.phone = party.phone,
                    p.email = party.email
                ON MATCH SET
                    p.city = COALESCE(party.city, p.city),
                    p.state = COALESCE(party.state, p.state),
                    p.phone = COALESCE(party.phone, p.phone),
                    p.email = COALESCE(party.email, p.email)
                WITH p, party
                MATCH (t:Trust {name: $trustName})
                MERGE (p)-[:SERVICES {role: party.role}]->(t)
                """,
                parties=parties_data,
                trustName=trust_name,
            )

        # 4. Tranches → Trust ISSUED Tranche
        if extraction.tranches:
            tranches_data = [
                {
                    "className": tr.class_name,
                    "cusip": tr.cusip,
                    "passThroughRate": tr.pass_through_rate,
                    "originalBalance": tr.original_balance,
                    "endingBalance": tr.ending_balance,
                    "currentCreditSupport": tr.current_credit_support,
                    "originalCreditSupport": tr.original_credit_support,
                    # Fallback key when CUSIP is null
                    "mergeKey": tr.cusip if tr.cusip else f"{tr.class_name}_{trust_name}",
                }
                for tr in extraction.tranches
            ]
            session.run(
                """
                UNWIND $tranches AS tr
                MERGE (tranche:Tranche {cusip: tr.mergeKey})
                ON CREATE SET
                    tranche.className = tr.className,
                    tranche.cusip = tr.cusip,
                    tranche.passThroughRate = tr.passThroughRate,
                    tranche.originalBalance = tr.originalBalance,
                    tranche.endingBalance = tr.endingBalance,
                    tranche.currentCreditSupport = tr.currentCreditSupport,
                    tranche.originalCreditSupport = tr.originalCreditSupport
                ON MATCH SET
                    tranche.endingBalance = COALESCE(tr.endingBalance, tranche.endingBalance),
                    tranche.currentCreditSupport = COALESCE(tr.currentCreditSupport, tranche.currentCreditSupport)
                WITH tranche
                MATCH (t:Trust {name: $trustName})
                MERGE (t)-[:ISSUED]->(tranche)
                """,
                tranches=tranches_data,
                trustName=trust_name,
            )

        # 5. Loans → Trust CONTAINS_LOAN Loan
        if extraction.loans:
            loans_data = [
                {
                    "prosId": lo.pros_id,
                    "loanId": lo.loan_id,
                    "propertyType": lo.property_type,
                    "city": lo.city,
                    "state": lo.state,
                    "grossRate": lo.gross_rate,
                    "interestAccrualType": lo.interest_accrual_type,
                    "maturityDate": lo.maturity_date,
                    "anticipatedRepayDate": lo.anticipated_repay_date,
                    "originalBalance": lo.original_balance,
                    "endingBalance": lo.ending_balance,
                    "isInterestOnly": lo.is_interest_only,
                }
                for lo in extraction.loans
            ]
            session.run(
                """
                UNWIND $loans AS loan
                MERGE (l:Loan {prosId: loan.prosId, trustName: $trustName})
                ON CREATE SET
                    l.loanId = loan.loanId,
                    l.propertyType = loan.propertyType,
                    l.city = loan.city,
                    l.state = loan.state,
                    l.grossRate = loan.grossRate,
                    l.interestAccrualType = loan.interestAccrualType,
                    l.maturityDate = loan.maturityDate,
                    l.anticipatedRepayDate = loan.anticipatedRepayDate,
                    l.originalBalance = loan.originalBalance,
                    l.endingBalance = loan.endingBalance,
                    l.isInterestOnly = loan.isInterestOnly
                ON MATCH SET
                    l.endingBalance = COALESCE(loan.endingBalance, l.endingBalance),
                    l.loanId = COALESCE(loan.loanId, l.loanId),
                    l.propertyType = COALESCE(loan.propertyType, l.propertyType),
                    l.city = COALESCE(loan.city, l.city),
                    l.state = COALESCE(loan.state, l.state)
                WITH l
                MATCH (t:Trust {name: $trustName})
                MERGE (t)-[:CONTAINS_LOAN]->(l)
                """,
                loans=loans_data,
                trustName=trust_name,
            )

        # 6. LoanSnapshots → Filing HAS_SNAPSHOT, Snapshot SNAPSHOT_OF Loan
        if extraction.loan_snapshots:
            snapshots_data = [
                {
                    "prosId": s.pros_id,
                    "endingBalance": s.ending_balance,
                    "scheduledInterest": s.scheduled_interest,
                    "scheduledPrincipal": s.scheduled_principal,
                    "paidThroughDate": s.paid_through_date,
                    "monthsDelinquent": s.months_delinquent,
                    "mortgageLoanStatus": s.mortgage_loan_status,
                    "outstandingPiAdvances": s.outstanding_pi_advances,
                    "actualBalance": s.actual_balance,
                    "mostRecentNoi": s.most_recent_noi,
                }
                for s in extraction.loan_snapshots
            ]
            session.run(
                """
                UNWIND $snapshots AS snap
                MERGE (s:LoanSnapshot {accessionNumber: $accession, prosId: snap.prosId})
                ON CREATE SET
                    s.endingBalance = snap.endingBalance,
                    s.scheduledInterest = snap.scheduledInterest,
                    s.scheduledPrincipal = snap.scheduledPrincipal,
                    s.paidThroughDate = snap.paidThroughDate,
                    s.monthsDelinquent = snap.monthsDelinquent,
                    s.mortgageLoanStatus = snap.mortgageLoanStatus,
                    s.outstandingPiAdvances = snap.outstandingPiAdvances,
                    s.actualBalance = snap.actualBalance,
                    s.mostRecentNoi = snap.mostRecentNoi
                WITH s, snap
                MATCH (f:Filing {accessionNumber: $accession})
                MERGE (f)-[:HAS_SNAPSHOT]->(s)
                WITH s, snap
                MATCH (l:Loan {prosId: snap.prosId, trustName: $trustName})
                MERGE (s)-[:SNAPSHOT_OF]->(l)
                """,
                snapshots=snapshots_data,
                accession=accession,
                trustName=trust_name,
            )

        # 7. Specially Serviced — enrich existing Loan nodes
        if extraction.specially_serviced:
            ss_data = [
                {
                    "prosId": ss.pros_id,
                    "loanId": ss.loan_id,
                    "appraisalValue": ss.appraisal_value,
                    "appraisalDate": ss.appraisal_date,
                    "noi": ss.noi,
                    "dscr": ss.dscr,
                    "servicingTransferDate": ss.servicing_transfer_date,
                    "resolutionStrategyCode": ss.resolution_strategy_code,
                    "specialServicingComments": ss.special_servicing_comments,
                }
                for ss in extraction.specially_serviced
            ]
            session.run(
                """
                UNWIND $ssLoans AS ss
                MATCH (l:Loan {prosId: ss.prosId, trustName: $trustName})
                SET l.isSpeciallyServiced = true,
                    l.appraisalValue = ss.appraisalValue,
                    l.appraisalDate = ss.appraisalDate,
                    l.specialServicingNoi = ss.noi,
                    l.specialServicingDscr = ss.dscr,
                    l.specialServicingTransferDate = ss.servicingTransferDate,
                    l.resolutionStrategyCode = ss.resolutionStrategyCode,
                    l.specialServicingComments = ss.specialServicingComments
                """,
                ssLoans=ss_data,
                trustName=trust_name,
            )

    return {
        "trust": trust_name,
        "accession": accession,
        "parties": len(extraction.parties),
        "tranches": len(extraction.tranches),
        "loans": len(extraction.loans),
        "snapshots": len(extraction.loan_snapshots),
        "specially_serviced": len(extraction.specially_serviced),
    }
