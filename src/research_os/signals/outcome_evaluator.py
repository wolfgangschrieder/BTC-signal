from __future__ import annotations
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
from research_os.signals.outcomes import OutcomeStatus
from research_os.signals.outcome_repository import SignalOutcomeRepository
from research_os.signals.execution import ExecutionStatus,evaluate_candle

class SignalOutcomeEvaluator:
    """Resolves live signals against future 1m OHLC candles.

    Entry is considered filled when candle range touches the entry zone.
    If SL and TP1 are both touched in the same OHLC candle, the outcome is ambiguous because
    intrabar ordering is unknowable from OHLC data.
    """
    def __init__(self,horizon_minutes:int=60): self.horizon_minutes=horizon_minutes
    def resolve_pending(self,session:Session,now:datetime|None=None)->int:
        now=now or datetime.now(timezone.utc); repo=SignalOutcomeRepository(); resolved=0
        for s in repo.pending(session,now):
            horizon=s["horizon_minutes"] or self.horizon_minutes
            candles=session.execute(text("""SELECT event_time,open,high,low,close FROM market.candles
                WHERE symbol=:symbol AND interval='1' AND event_time>:time AND event_time<=:until
                AND point_in_time_available_at<=:now ORDER BY event_time"""),
                {"symbol":s["symbol"],"time":s["signal_time"],"until":s["signal_time"]+timedelta(minutes=horizon),"now":now}).mappings().all()
            if not candles: continue
            entry=None; best_mfe=0.0; worst_mae=0.0
            for c in candles:
                high=float(c["high"]); low=float(c["low"])
                if entry is None:
                    probe=evaluate_candle(
                        s["direction"], entry_price=float(s["entry_price"]),
                        stop_loss=float(s["stop_loss"]), take_profit=float(s["tp1"]),
                        high=high, low=low,
                    )
                    if probe.status is ExecutionStatus.NO_FILL:
                        continue
                    entry=float(s["entry_price"])
                direction=s["direction"]
                if direction=="long":
                    best_mfe=max(best_mfe,(high-entry)/entry)
                    worst_mae=min(worst_mae,(low-entry)/entry)
                else:
                    best_mfe=max(best_mfe,(entry-low)/entry)
                    worst_mae=min(worst_mae,(high-entry)/entry)
                result=evaluate_candle(
                    direction, entry_price=entry,
                    stop_loss=float(s["stop_loss"]), take_profit=float(s["tp1"]),
                    high=high, low=low,
                )
                if result.status in (ExecutionStatus.NO_FILL,ExecutionStatus.PENDING):
                    continue
                if result.status is ExecutionStatus.AMBIGUOUS:
                    repo.resolve(session,s["signal_id"],OutcomeStatus.AMBIGUOUS,None,best_mfe,worst_mae,c["event_time"],result.reason); resolved+=1; break
                repo.resolve(
                    session,s["signal_id"],
                    OutcomeStatus.WIN if result.status is ExecutionStatus.WIN else OutcomeStatus.LOSS,
                    result.realized_return,best_mfe,worst_mae,c["event_time"],None,
                ); resolved+=1; break
            else:
                if now >= s["signal_time"]+timedelta(minutes=horizon):
                    repo.resolve(session,s["signal_id"],OutcomeStatus.EXPIRED,None,best_mfe,worst_mae,now,"horizon expired without TP1/SL"); resolved+=1
        session.commit(); return resolved
