from __future__ import annotations
from sqlalchemy import text

class CrossMarketOutcomeRepository:
    def save(self,session,outcome,symbol="BTCUSDT"):
        session.execute(text("""
            INSERT INTO research.cross_market_outcomes
            (symbol,asset,state_timestamp,outcome_timestamp,horizon_minutes,
             normalized_value,btc_return_pct,btc_mfe_pct,btc_mae_pct)
            VALUES (:symbol,:asset,:state_timestamp,:outcome_timestamp,:horizon,
                    :normalized_value,:return_pct,:mfe_pct,:mae_pct)
            ON CONFLICT (symbol,asset,state_timestamp,horizon_minutes) DO NOTHING
        """),{
            "symbol":symbol,"asset":outcome.asset,
            "state_timestamp":outcome.state_timestamp,
            "outcome_timestamp":outcome.outcome_timestamp,
            "horizon":outcome.horizon_minutes,
            "normalized_value":outcome.normalized_value,
            "return_pct":outcome.btc_return_pct,
            "mfe_pct":outcome.btc_mfe_pct,
            "mae_pct":outcome.btc_mae_pct,
        })

    def load(self,session,symbol="BTCUSDT",asset=None):
        sql="""SELECT symbol,asset,state_timestamp,outcome_timestamp,
                      horizon_minutes,normalized_value,btc_return_pct,
                      btc_mfe_pct,btc_mae_pct
               FROM research.cross_market_outcomes
               WHERE symbol=:symbol"""
        params={"symbol":symbol}
        if asset:
            sql+=" AND asset=:asset"; params["asset"]=asset
        sql+=" ORDER BY state_timestamp"
        return [dict(row) for row in session.execute(text(sql),params).mappings().all()]
