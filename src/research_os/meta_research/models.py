from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field

class FindingStatus(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    HYPOTHESIZED = "hypothesized"
    TESTED = "tested"
    REPLICATED = "replicated"
    REFUTED = "refuted"
    UNKNOWN = "unknown"

class AuditFinding(BaseModel):
    finding_id: str
    audit_time: datetime
    category: str
    status: FindingStatus
    statement: str
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    recommended_research_action: str | None = None

    model_config = {"extra": "forbid"}
