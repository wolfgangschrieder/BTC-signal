from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from research_os.cross_market.models import CrossMarketObservation
from research_os.intelligence.events import ExternalEvent

from .research_dataset import ResearchDataset


@dataclass(frozen=True, slots=True)
class DatasetLeakageViolation:
    decision_time: datetime
    source: str
    source_id: str
    available_at: datetime


def audit_dataset_evidence(
    dataset: ResearchDataset,
    *,
    external_events: tuple[ExternalEvent, ...] = (),
    cross_market_observations: tuple[CrossMarketObservation, ...] = (),
) -> tuple[DatasetLeakageViolation, ...]:
    violations: list[DatasetLeakageViolation] = []

    for row in dataset.rows:
        if row.outcome_time <= row.decision_time:
            violations.append(
                DatasetLeakageViolation(row.decision_time, "outcome", row.symbol, row.outcome_time)
            )

        event_ids = set(row.external_event_ids)
        for event in external_events:
            if event.event_id in event_ids and event.point_in_time_available_at > row.decision_time:
                violations.append(
                    DatasetLeakageViolation(
                        row.decision_time, "external_event", event.event_id,
                        event.point_in_time_available_at,
                    )
                )

        assets = {item[0] for item in row.cross_market}
        for observation in cross_market_observations:
            if (
                observation.asset in assets
                and observation.timestamp <= row.decision_time
                and observation.point_in_time_available_at > row.decision_time
            ):
                violations.append(
                    DatasetLeakageViolation(
                        row.decision_time, "cross_market", observation.asset,
                        observation.point_in_time_available_at,
                    )
                )

    return tuple(
        sorted(
            violations,
            key=lambda item: (
                item.decision_time,
                item.source,
                item.source_id,
                item.available_at,
            ),
        )
    )
