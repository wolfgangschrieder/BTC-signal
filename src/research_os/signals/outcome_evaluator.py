from __future__ import annotations
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
from research_os.signals.outcomes import OutcomeStatus
from research_os.signals.outcome_repository import SignalOutcomeRepository

class SignalOutcomeEvaluator:
    """Resolves live signals against future 1m OHLC candles.

    Entry is considered filled when candle range touches the entry zone.
    If SL and TP1 are both touched in the same OHLC candle, LOSS wins because
    intrabar ordering is unknowable without finer-grained data.
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
                high=float(c["high"]); low=float(c["low"]); close=float(c["close"])
                if entry is None:
                    if low<=float(s["entry_price"])<=high or low<=float(s["entry_price"]) and high>=float(s["entry_price"]):
                        entry=float(s["entry_price"])
                    else: continue
                direction=s["direction"]; sl=float(s["stop_loss"]); tp=float(s["tp1"])
                if direction=="long":
                    best_mfe=max(best_mfe,(high-entry)/entry); worst_mae=min(worst_mae,(low-entry)/entry)
                    hit_sl=low<=sl; hit_tp=high>=tp
                    if hit_sl or hit_tp:
                        status=OutcomeStatus.LOSS if hit_sl else OutcomeStatus.WIN
                        exit_price=sl if hit_sl else tp
                        repo.resolve(session,s["signal_id"],status,(exit_price-entry)/entry,best_mfe,worst_mae,c["event_time"],"both SL and TP touched" if hit_sl and hit_tp else None); resolved+=1; break
                else:
                    best_mfe=max(best_mfe,(entry-low)/entry); worst_mae=min(worst_mae,(high-entry)/entry)
                    hit_sl=high>=sl; hit_tp=low<=tp
                    if hit_sl or hit_tp:
                        status=OutcomeStatus.LOSS if hit_sl else OutcomeStatus.WIN
                        exit_price=sl if hit_sl else tp
                        repo.resolve(session,s["signal_id"],status,(entry-exit_price)/entry,best_mfe,worst_mae,c["event_time"],"both SL and TP touched" if hit_sl and hit_tp else None); resolved+=1; break
            else:
                if now >= s["signal_time"]+timedelta(minutes=horizon):
                    repo.resolve(session,s["signal_id"],OutcomeStatus.EXPIRED,None,best_mfe,worst_mae,now,"horizon expired without TP1/SL"); resolved+=1
        session.commit(); return resolved
