from __future__ import annotations
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
from research_os.signals.outcomes import OutcomeStatus, SignalOutcome

class SignalOutcomeRepository:
    def record_pending(self,session:Session,outcome:SignalOutcome)->None:
        session.execute(text("""INSERT INTO signal_outcomes
        (signal_id,symbol,direction,signal_time,entry_price,stop_loss,tp1,tp2,tp3,probability,status,horizon_minutes,reason,fee_bps,slippage_bps,execution_policy,research_score,probability_model_id,calibration_context)
        VALUES (:id,:symbol,:direction,:time,:entry,:sl,:tp1,:tp2,:tp3,:prob,:status,:horizon,:reason,:fee,:slippage,:policy,:score,:model_id,:context)
        ON CONFLICT (signal_id) DO NOTHING"""),dict(id=outcome.signal_id,symbol=outcome.symbol,direction=outcome.direction, time=outcome.signal_time,entry=outcome.entry_price,sl=outcome.stop_loss,tp1=outcome.tp1,tp2=outcome.tp2,tp3=outcome.tp3,prob=outcome.probability,status=outcome.status.value,horizon=outcome.horizon_minutes,reason=outcome.reason,fee=outcome.fee_bps,slippage=outcome.slippage_bps,policy=outcome.execution_policy,score=outcome.research_score,model_id=outcome.probability_model_id,context=outcome.calibration_context))

    def latest_emissions(self, session: Session, symbol: str):
        return session.execute(text("""SELECT symbol,direction,max(signal_time) AS signal_time
            FROM signal_outcomes WHERE symbol=:symbol GROUP BY symbol,direction"""),
            {"symbol": symbol}).mappings().all()

    def summary(self,session:Session,since:datetime)->dict:
        rows=session.execute(text("""SELECT status, count(*) FROM signal_outcomes
        WHERE resolved_at >= :since AND status IN ('win','loss','expired','ambiguous')
        GROUP BY status"""),{"since":since}).all()
        counts={str(k):int(v) for k,v in rows}
        wins=counts.get("win",0); losses=counts.get("loss",0)
        expired=counts.get("expired",0); ambiguous=counts.get("ambiguous",0)
        resolved=wins+losses+expired+ambiguous
        return {
            "total":resolved,
            "wins":wins,
            "losses":losses,
            "expired":expired,
            "ambiguous":ambiguous,
            "win_rate":wins/(wins+losses) if wins+losses else None,
        }

    def pending(self,session:Session,now:datetime):
        return session.execute(text("""SELECT signal_id,symbol,direction,signal_time,entry_price,stop_loss,tp1,tp2,tp3,probability,horizon_minutes,fee_bps,slippage_bps,execution_policy
        FROM signal_outcomes WHERE status='pending' AND signal_time < :now ORDER BY signal_time"""),{"now":now}).mappings().all()

    def resolve(self,session:Session,signal_id,status,realized_return=None,mfe=None,mae=None,resolved_at=None,reason=None):
        session.execute(text("""UPDATE signal_outcomes SET status=:status,realized_return=:ret,mfe=:mfe,mae=:mae,resolved_at=:resolved,reason=:reason WHERE signal_id=:id"""),
                        {"status":status.value if hasattr(status,"value") else status,"ret":realized_return,"mfe":mfe,"mae":mae,"resolved":resolved_at or datetime.now(timezone.utc),"reason":reason,"id":signal_id})
