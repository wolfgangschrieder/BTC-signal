from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from research_os.cross_market.models import CrossMarketObservation
from research_os.cross_market.repository import CrossMarketRepository
from research_os.intelligence.event_repository import ExternalEventRepository
from research_os.intelligence.events import ExternalEventEngine
from research_os.research.dataset import ResearchDatasetRow, build_dataset_row


class ResearchDatasetRepository:
    """Build and persist PIT-safe dataset rows from resolved signals."""

    def __init__(
        self,
        cross_market: CrossMarketRepository | None = None,
        external_events: ExternalEventRepository | None = None,
    ) -> None:
        self.cross_market = cross_market or CrossMarketRepository()
        self.external_events = external_events or ExternalEventRepository()

    def build_resolved(
        self,
        session: Session,
        *,
        dataset_version: str = "research-dataset-v1",
        symbol: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        horizons: tuple[int, ...] = (15, 60, 240),
    ) -> int:
        """Materialize resolved outcomes whose state and evidence are PIT-valid."""
        if not horizons:
            raise ValueError("horizons must not be empty")

        where=[
            "o.status IN ('win','loss','expired')",
            "o.realized_return IS NOT NULL",
            "o.mfe IS NOT NULL",
            "o.mae IS NOT NULL",
            "o.horizon_minutes = ANY(:horizons)",
        ]
        params={"version":dataset_version,"horizons":list(horizons)}
        if symbol:
            where.append("o.symbol=:symbol"); params["symbol"]=symbol
        if start:
            where.append("o.signal_time>=:start"); params["start"]=start
        if end:
            where.append("o.signal_time<=:end"); params["end"]=end

        rows=session.execute(text(f"""
            SELECT o.signal_id,o.symbol,o.direction,o.signal_time,o.entry_price,
                   o.probability,o.horizon_minutes,o.realized_return,o.mfe,o.mae,o.resolved_at,
                   s.state_id,s.timestamp,s.decision_time,s.point_in_time_available_at,
                   s.vector,s.provenance
            FROM signal_outcomes o
            JOIN world.market_state_vectors s
              ON s.symbol=o.symbol AND s.timestamp=o.signal_time
            WHERE {' AND '.join(where)}
              AND s.point_in_time_available_at<=o.signal_time
            ORDER BY o.signal_time,o.symbol,o.horizon_minutes,o.signal_id
        """),params).mappings().all()

        inserted=0
        for row in rows:
            decision_time=row["signal_time"]
            cm_values={}
            cm_sources={}
            for asset in ("DOLLAR_BROAD","SPX","NASDAQ","VIX","US10Y"):
                item=self.cross_market.latest(session,asset,decision_time)
                if item:
                    cm_values[asset]=float(item["value"])
                    cm_sources[asset]=item["source"]
            cross_market={"values":cm_values,"sources":cm_sources,"available":bool(cm_values)}

            events=self.external_events.latest(
                session,decision_time,lookback_seconds=3600.0,limit=100
            )
            ext_snapshot=ExternalEventEngine().build(
                decision_time,events,as_of=decision_time,lookback_seconds=3600.0
            )
            external={
                "event_count":ext_snapshot.total_count,
                "high_impact_count":ext_snapshot.high_impact_count,
                "weighted_sentiment":ext_snapshot.weighted_sentiment,
                "max_relevance":ext_snapshot.max_relevance,
                "categories":ext_snapshot.categories,
                "event_ids":tuple(event.event_id for event in ext_snapshot.events),
            }

            dataset_row=build_dataset_row(
                dataset_version=dataset_version,
                state={
                    "state_id":row["state_id"],
                    "timestamp":row["timestamp"],
                    "point_in_time_available_at":row["point_in_time_available_at"],
                    "vector":row["vector"],
                },
                outcome={
                    "symbol":row["symbol"],"direction":row["direction"],
                    "signal_time":row["signal_time"],"entry_price":row["entry_price"],
                    "probability":row["probability"],"horizon_minutes":row["horizon_minutes"],
                    "resolved_at":row["resolved_at"],"realized_return":row["realized_return"],
                    "mfe":row["mfe"],"mae":row["mae"],
                },
                cross_market=cross_market,
                external=external,
            )
            self.save(session,dataset_row)
            inserted+=1
        return inserted

    def save(self, session: Session, row: ResearchDatasetRow) -> None:
        session.execute(text("""
            INSERT INTO research.research_dataset_rows
            (dataset_version,symbol,decision_time,entry_price,horizon_minutes,outcome_time,
             return_pct,mfe_pct,mae_pct,features,cross_market,external_event_count,
             external_high_impact_count,external_weighted_sentiment,external_max_relevance,
             external_categories,external_event_ids,provenance)
            VALUES (:version,:symbol,:decision_time,:entry,:horizon,:outcome_time,
                    :return_pct,:mfe_pct,:mae_pct,CAST(:features AS jsonb),CAST(:cross_market AS jsonb),
                    :event_count,:high_impact,:weighted_sentiment,:max_relevance,
                    CAST(:categories AS jsonb),CAST(:event_ids AS jsonb),CAST(:provenance AS jsonb))
            ON CONFLICT (dataset_version,symbol,decision_time,horizon_minutes) DO NOTHING
        """),{
            "version":row.dataset_version,"symbol":row.symbol,"decision_time":row.decision_time,
            "entry":row.entry_price,"horizon":row.horizon_minutes,"outcome_time":row.outcome_time,
            "return_pct":row.return_pct,"mfe_pct":row.mfe_pct,"mae_pct":row.mae_pct,
            "features":json.dumps(row.features,default=str),"cross_market":json.dumps(row.cross_market,default=str),
            "event_count":row.external_event_count,"high_impact":row.external_high_impact_count,
            "weighted_sentiment":row.external_weighted_sentiment,"max_relevance":row.external_max_relevance,
            "categories":json.dumps(row.external_categories),"event_ids":json.dumps(row.external_event_ids),
            "provenance":json.dumps(row.provenance,default=str),
        })
