from datetime import datetime, timedelta, timezone

from research_os.intelligence.events import EventCategory, EventImpact, ExternalEvent
from research_os.research.dataset_leakage import audit_dataset_evidence
from research_os.research.research_dataset import ResearchDataset, ResearchDatasetRow


def make_row(t, event_ids=()):
    return ResearchDatasetRow(
        "BTCUSDT", t, 100.0, 1, t + timedelta(minutes=1),
        0.01, 0.02, -0.01, (), (), len(event_ids), 0, None, 0.0, (), tuple(event_ids)
    )


def make_event(t, pit):
    return ExternalEvent("evt", "event", "test", t, pit, EventCategory.MACRO, EventImpact.HIGH, 1.0, 0.0, 1.0)


def test_audit_detects_future_external_availability():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dataset = ResearchDataset("BTCUSDT", "v1", (make_row(t, ("evt",)),), 0)
    violations = audit_dataset_evidence(dataset, external_events=(make_event(t, t + timedelta(seconds=1)),))
    assert len(violations) == 1
    assert violations[0].source == "external_event"


def test_clean_dataset_has_no_violations():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dataset = ResearchDataset("BTCUSDT", "v1", (make_row(t, ("evt",)),), 0)
    assert audit_dataset_evidence(dataset, external_events=(make_event(t, t),)) == ()
