"""Database provenance boundary for frozen calibration models."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

from research_os.research.calibration_model import CalibrationArtifact, ForecastSample


class CalibrationModelRepository:
    def load_samples(self, session, *, symbol, direction, context_id, as_of):
        rows = (
            session.execute(
                text("""
            SELECT signal_id,symbol,direction,signal_time,resolved_at,horizon_minutes,
                   research_score,status,calibration_context
            FROM signal_outcomes
            WHERE symbol=:symbol AND direction=:direction AND calibration_context=:context
              AND research_score IS NOT NULL AND probability_model_id IS NULL
              AND execution_policy='conservative-midpoint-v2'
              AND status IN ('win','loss','expired','ambiguous')
              AND resolved_at<=:as_of
            ORDER BY signal_time,signal_id
        """),
                {"symbol": symbol, "direction": direction, "context": context_id, "as_of": as_of},
            )
            .mappings()
            .all()
        )
        return tuple(
            ForecastSample(
                row["signal_id"],
                row["symbol"],
                row["direction"],
                row["signal_time"],
                max(
                    row["resolved_at"],
                    row["signal_time"] + timedelta(minutes=row["horizon_minutes"] or 60),
                ),
                float(row["research_score"]),
                row["status"],
                row["calibration_context"],
            )
            for row in rows
            if row["signal_time"] + timedelta(minutes=row["horizon_minutes"] or 60) <= as_of
        )

    def save(self, session, artifact: CalibrationArtifact):
        session.execute(
            text("""
            INSERT INTO intelligence.calibration_models (model_id,symbol,direction,context_id,artifact,accepted,created_at)
            VALUES (:id,:symbol,:direction,:context,CAST(:artifact AS jsonb),:accepted,:created)
            ON CONFLICT (model_id) DO NOTHING
        """),
            {
                "id": artifact.model_id,
                "symbol": artifact.symbol,
                "direction": artifact.direction,
                "context": artifact.context_id,
                "artifact": artifact.model_dump_json(),
                "accepted": not artifact.rejection_reasons(),
                "created": artifact.created_at,
            },
        )
        return artifact.model_id

    def load(self, session, model_id: str):
        row = (
            session.execute(
                text("SELECT artifact FROM intelligence.calibration_models WHERE model_id=:id"),
                {"id": model_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ValueError("calibration model not found")
        return CalibrationArtifact.model_validate(row["artifact"])
