"""Pydantic v2 models for CMBS 10-D filing extraction.

All financial fields are float | None (Neo4j stores floats, Kimi returns JSON floats).
Dates are str | None — the loader handles conversion.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TrustInfo(BaseModel):
    name: str
    series: str | None = None
    original_balance: float | None = Field(None, alias="originalBalance")
    current_balance: float | None = Field(None, alias="currentBalance")
    loan_count: int | None = Field(None, alias="loanCount")
    property_count: int | None = Field(None, alias="propertyCount")
    wac: float | None = None
    weighted_avg_dscr: float | None = Field(None, alias="weightedAvgDscr")


class FilingInfo(BaseModel):
    accession_number: str = Field(..., alias="accessionNumber")
    distribution_date: str | None = Field(None, alias="distributionDate")
    determination_date: str | None = Field(None, alias="determinationDate")
    total_interest: float | None = Field(None, alias="totalInterest")
    total_principal: float | None = Field(None, alias="totalPrincipal")
    total_distributed: float | None = Field(None, alias="totalDistributed")


class PartyInfo(BaseModel):
    name: str
    role: str
    city: str | None = None
    state: str | None = None
    phone: str | None = None
    email: str | None = None


class TrancheInfo(BaseModel):
    class_name: str = Field(..., alias="className")
    cusip: str | None = None
    pass_through_rate: float | None = Field(None, alias="passThroughRate")
    original_balance: float | None = Field(None, alias="originalBalance")
    ending_balance: float | None = Field(None, alias="endingBalance")
    current_credit_support: float | None = Field(None, alias="currentCreditSupport")
    original_credit_support: float | None = Field(None, alias="originalCreditSupport")


class LoanInfo(BaseModel):
    pros_id: str = Field(..., alias="prosId")
    loan_id: str | None = Field(None, alias="loanId")
    property_type: str | None = Field(None, alias="propertyType")
    city: str | None = None
    state: str | None = None
    gross_rate: float | None = Field(None, alias="grossRate")
    interest_accrual_type: str | None = Field(None, alias="interestAccrualType")
    maturity_date: str | None = Field(None, alias="maturityDate")
    anticipated_repay_date: str | None = Field(None, alias="anticipatedRepayDate")
    original_balance: float | None = Field(None, alias="originalBalance")
    ending_balance: float | None = Field(None, alias="endingBalance")
    is_interest_only: bool | None = Field(None, alias="isInterestOnly")


class LoanSnapshotInfo(BaseModel):
    pros_id: str = Field(..., alias="prosId")
    ending_balance: float | None = Field(None, alias="endingBalance")
    scheduled_interest: float | None = Field(None, alias="scheduledInterest")
    scheduled_principal: float | None = Field(None, alias="scheduledPrincipal")
    paid_through_date: str | None = Field(None, alias="paidThroughDate")
    months_delinquent: int | None = Field(None, alias="monthsDelinquent")
    mortgage_loan_status: str | None = Field(None, alias="mortgageLoanStatus")
    outstanding_pi_advances: float | None = Field(None, alias="outstandingPiAdvances")
    actual_balance: float | None = Field(None, alias="actualBalance")
    most_recent_noi: float | None = Field(None, alias="mostRecentNoi")


class SpeciallyServicedInfo(BaseModel):
    pros_id: str = Field(..., alias="prosId")
    loan_id: str | None = Field(None, alias="loanId")
    appraisal_value: float | None = Field(None, alias="appraisalValue")
    appraisal_date: str | None = Field(None, alias="appraisalDate")
    noi: float | None = None
    dscr: float | None = None
    servicing_transfer_date: str | None = Field(None, alias="servicingTransferDate")
    resolution_strategy_code: str | None = Field(None, alias="resolutionStrategyCode")
    special_servicing_comments: str | None = Field(None, alias="specialServicingComments")


class FilingExtraction(BaseModel):
    """Top-level model wrapping everything extracted from one MD file."""

    trust: TrustInfo
    filing: FilingInfo
    parties: list[PartyInfo] = Field(default_factory=list)
    tranches: list[TrancheInfo] = Field(default_factory=list)
    loans: list[LoanInfo] = Field(default_factory=list)
    loan_snapshots: list[LoanSnapshotInfo] = Field(
        default_factory=list, alias="loanSnapshots"
    )
    specially_serviced: list[SpeciallyServicedInfo] = Field(
        default_factory=list, alias="speciallyServiced"
    )

    model_config = {"populate_by_name": True}
