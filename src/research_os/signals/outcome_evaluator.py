from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from research_os.signals.execution import ExecutionStatus, evaluate_candle
from research_os.signals.outcome_repository import SignalOutcomeRepository
from research_os.signals.outcomes import OutcomeStatus


class SignalOutcomeEvaluator:
    """Resolves live signals against future 1m OHLC candles.

    signal_time is the decision time, never the source candle open time.
    Only candles opening strictly after that decision can fill an entry;
    new conservative policies flag an entry candle touching TP/SL as ambiguous.
    Historical signals retain their persisted execution policy and costs.

    Entry is modeled as a limit at the persisted entry-zone midpoint.
    It is not a market-order or arbitrary-zone-fill simulation.
    If SL and TP1 are both touched in the same OHLC candle, the outcome is ambiguous because
    intrabar ordering is unknowable from OHLC data.
    """
    def __init__(self,horizon_minutes:int=60): self.horizon_minutes=horizon_minutes
    def resolve_pending(self,session:Session,now:datetime|None=None)->int:
        now=now or datetime.now(UTC); repo=SignalOutcomeRepository(); resolved=0
        for s in repo.pending(session,now):
            horizon=s["horizon_minutes"] or self.horizon_minutes
            candles=session.execute(text("""SELECT event_time,open,high,low,close FROM market.candles
                WHERE symbol=:symbol AND interval='1' AND event_time>:time AND event_time<=:until
                AND point_in_time_available_at<=:now ORDER BY event_time"""),
                {"symbol":s["symbol"],"time":s["signal_time"],"until":s["signal_time"]+timedelta(minutes=horizon),"now":now}).mappings().all()
            entry=None; best_mfe=0.0; worst_mae=0.0
            for c in candles:
                high=float(c["high"]); low=float(c["low"])
                if entry is None:
                    fill=evaluate_candle(
                        s["direction"], entry_price=float(s["entry_price"]),
                        stop_loss=float(s["stop_loss"]), take_profit=float(s["tp1"]),
                        high=high, low=low, check_exit=False,
                        fee_bps=s.get("fee_bps",0), slippage_bps=s.get("slippage_bps",0),
                        conservative_entry=s.get("execution_policy") == "conservative-midpoint-v2",
                    )
                    if fill.status is ExecutionStatus.NO_FILL:
                        continue
                    if fill.status is ExecutionStatus.AMBIGUOUS:
                        repo.resolve(session,s["signal_id"],OutcomeStatus.AMBIGUOUS,None,best_mfe,worst_mae,c["event_time"],fill.reason)
                        resolved+=1
                        break
                    entry=fill.entry_price
                    continue
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
                    high=high, low=low, entry_filled=True,
                    fee_bps=s.get("fee_bps",0), slippage_bps=s.get("slippage_bps",0),
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
