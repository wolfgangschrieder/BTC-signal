from research_os.meta_research.auditor import MetaResearchAuditor
from research_os.meta_research.models import FindingStatus

def test_meta_research_is_research_only():
    finding = MetaResearchAuditor().audit()[0]
    assert finding.status is FindingStatus.OBSERVED
    assert "production" in finding.statement.lower()
    assert not hasattr(finding, "execute_trade")
