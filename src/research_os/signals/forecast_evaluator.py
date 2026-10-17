"""Direction-only research labels; never interpreted as trade P&L.

Reference: last closed 1m candle known at decision time (maximum age 2m).
Endpoint: last full minute ending no later than decision + horizon.
Partial decision/end minutes are excluded from excursions. All intervening
full candles must be present. Late backfills may supply future labels but
cannot replace information that was unavailable at the original decision.
"""
from datetime import UTC, datetime, timedelta
from sqlalchemy import text


def forecast_metrics(direction, reference_price, candles):
    if direction not in ("long", "short") or reference_price <= 0 or not candles:
        raise ValueError("valid direction, positive reference and candles required")
    sign = 1 if direction == "long" else -1
    endpoint = float(candles[-1]["close"])
    favorable = max(float(c["high"]) for c in candles) if sign == 1 else min(float(c["low"]) for c in candles)
    adverse = min(float(c["low"]) for c in candles) if sign == 1 else max(float(c["high"]) for c in candles)
    return (sign * (endpoint / reference_price - 1),
            max(0.0, sign * (favorable / reference_price - 1)),
            min(0.0, sign * (adverse / reference_price - 1)))


class SignalForecastEvaluator:
    horizons = (15, 30, 60)

    def resolve(self, session, now=None):
        now = now or datetime.now(UTC)
        # Include already-resolved execution scenarios: forecast life is independent.
        session.execute(text("""INSERT INTO signal_forecasts(signal_id,horizon_minutes)
            SELECT s.signal_id,h.minutes FROM signal_outcomes s
            CROSS JOIN (VALUES (15),(30),(60)) AS h(minutes)
            ON CONFLICT DO NOTHING"""))
        rows = session.execute(text("""SELECT f.*,s.symbol,s.direction,s.signal_time
            FROM signal_forecasts f JOIN signal_outcomes s USING(signal_id)
            WHERE f.status='pending' AND s.signal_time + f.horizon_minutes * interval '1 minute' <= :now
            ORDER BY s.signal_time LIMIT 500"""), {"now": now}).mappings().all()
        completed = 0
        for row in rows:
            decision = row["signal_time"]
            end = (decision + timedelta(minutes=row["horizon_minutes"])).replace(second=0, microsecond=0)
            start = decision.replace(second=0, microsecond=0)
            if start < decision:
                start += timedelta(minutes=1)
            reference = session.execute(text("""SELECT event_time,close FROM market.candles
                WHERE symbol=:symbol AND interval='1'
                AND event_time + interval '1 minute' <= :decision
                AND event_time + interval '1 minute' >= :decision - interval '2 minutes'
                AND point_in_time_available_at <= :decision
                ORDER BY event_time DESC LIMIT 1"""),
                {"symbol":row["symbol"],"decision":decision}).mappings().first()
            candles = session.execute(text("""SELECT event_time,high,low,close FROM market.candles
                WHERE symbol=:symbol AND interval='1' AND event_time>=:start
                AND event_time < :end AND point_in_time_available_at<=:now
                ORDER BY event_time"""),
                {"symbol":row["symbol"],"start":start,"end":end,"now":now}).mappings().all()
            expected = int((end-start).total_seconds() / 60)
            complete = len(candles) == expected and expected > 0 and all(
                c["event_time"] == start + timedelta(minutes=i) for i,c in enumerate(candles))
            # Retry gaps for 24h; keep insufficient labels explicit thereafter.
            if (reference is None or not complete) and now < end + timedelta(hours=24):
                continue
            metrics = forecast_metrics(row["direction"],float(reference["close"]),candles) if reference and complete else (None,None,None)
            session.execute(text("""UPDATE signal_forecasts SET status=:status,
                reference_price=:price,reference_time=:reference_time,
                reference_source='last_closed_1m_known_at_decision',endpoint_time=:end,
                directional_return=:ret,mfe=:mfe,mae=:mae,evaluated_at=:now,reason=:reason
                WHERE signal_id=:id AND horizon_minutes=:horizon"""),
                {"status":"completed" if reference and complete else "insufficient_data",
                 "price":float(reference["close"]) if reference else None,
                 "reference_time":reference["event_time"]+timedelta(minutes=1) if reference else None,
                 "end":end,"ret":metrics[0],"mfe":metrics[1],"mae":metrics[2],"now":now,
                 "reason":None if reference and complete else "missing decision-time reference or incomplete future candles",
                 "id":row["signal_id"],"horizon":row["horizon_minutes"]})
            completed += 1
        session.commit()
        return completed
