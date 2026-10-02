from __future__ import annotations

import json

from sqlalchemy import text

from .research_dataset import ResearchDataset


class ResearchDatasetRepository:
    def save(self, session, dataset: ResearchDataset) -> int:
        count = 0
        for row in dataset.rows:
            session.execute(
                text("""
                    INSERT INTO research.research_dataset_rows
                    (dataset_version,symbol,decision_time,entry_price,horizon_minutes,
                     outcome_time,return_pct,mfe_pct,mae_pct,features,cross_market,
                     external_event_count,external_high_impact_count,
                     external_weighted_sentiment,external_max_relevance,
                     external_categories,external_event_ids,provenance)
                    VALUES
                    (:version,:symbol,:decision_time,:entry_price,:horizon,
                     :outcome_time,:return_pct,:mfe_pct,:mae_pct,CAST(:features AS jsonb),
                     CAST(:cross_market AS jsonb),:event_count,:high_impact,
                     :weighted_sentiment,:max_relevance,CAST(:categories AS jsonb),
                     CAST(:event_ids AS jsonb),CAST(:provenance AS jsonb))
                    ON CONFLICT (dataset_version,symbol,decision_time,horizon_minutes)
                    DO UPDATE SET
                        entry_price=EXCLUDED.entry_price,
                        outcome_time=EXCLUDED.outcome_time,
                        return_pct=EXCLUDED.return_pct,
                        mfe_pct=EXCLUDED.mfe_pct,
                        mae_pct=EXCLUDED.mae_pct,
                        features=EXCLUDED.features,
                        cross_market=EXCLUDED.cross_market,
                        external_event_count=EXCLUDED.external_event_count,
                        external_high_impact_count=EXCLUDED.external_high_impact_count,
                        external_weighted_sentiment=EXCLUDED.external_weighted_sentiment,
                        external_max_relevance=EXCLUDED.external_max_relevance,
                        external_categories=EXCLUDED.external_categories,
                        external_event_ids=EXCLUDED.external_event_ids,
                        provenance=EXCLUDED.provenance
                """),
                {
                    "version": dataset.version,
                    "symbol": row.symbol,
                    "decision_time": row.decision_time,
                    "entry_price": row.entry_price,
                    "horizon": row.horizon_minutes,
                    "outcome_time": row.outcome_time,
                    "return_pct": row.return_pct,
                    "mfe_pct": row.mfe_pct,
                    "mae_pct": row.mae_pct,
                    "features": json.dumps(dict(row.features)),
                    "cross_market": json.dumps(row.cross_market),
                    "event_count": row.external_event_count,
                    "high_impact": row.external_high_impact_count,
                    "weighted_sentiment": row.external_weighted_sentiment,
                    "max_relevance": row.external_max_relevance,
                    "categories": json.dumps(row.external_categories),
                    "event_ids": json.dumps(row.external_event_ids),
                    "provenance": json.dumps([
                        {
                            "source": item.source,
                            "source_id": item.source_id,
                            "first_event_time": item.first_event_time.isoformat(),
                            "last_event_time": item.last_event_time.isoformat(),
                            "available_at": item.available_at.isoformat(),
                            "item_count": item.item_count,
                        }
                        for item in row.provenance
                    ]),
                },
            )
            count += 1
        return count

    def count(self, session, dataset_version: str, symbol: str) -> int:
        value = session.execute(
            text("SELECT COUNT(*) FROM research.research_dataset_rows WHERE dataset_version=:version AND symbol=:symbol"),
            {"version": dataset_version, "symbol": symbol},
        ).scalar_one()
        return int(value)

    def assert_pit_safe(self, session, dataset_version: str, symbol: str) -> int:
        value = session.execute(
            text("""
                SELECT COUNT(*) FROM research.research_dataset_rows
                WHERE dataset_version=:version AND symbol=:symbol
                  AND outcome_time <= decision_time
            """),
            {"version": dataset_version, "symbol": symbol},
        ).scalar_one()
        return int(value)
