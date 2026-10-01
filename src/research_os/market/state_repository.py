from __future__ import annotations
import json
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session
from research_os.market.state_vector import MarketStateVector

class MarketStateRepository:
    def save(self,session:Session,state:MarketStateVector)->None:
        session.execute(text("""
            INSERT INTO world.market_state_vectors
            (state_id,symbol,timestamp,decision_time,point_in_time_available_at,
             vector_version,feature_version,factor_version,regime_version,code_version,
             vector,market_state,data_quality,evidence,provenance)
            VALUES (:state_id,:symbol,:timestamp,:decision_time,:pit,
                    :vector_version,:feature_version,'factors-v1','regime-v1','runtime',
                    CAST(:vector AS jsonb),'unknown',CAST(:quality AS jsonb),'[]'::jsonb,CAST(:provenance AS jsonb))
            ON CONFLICT (state_id) DO NOTHING
        """),{
            "state_id":state.fingerprint,"symbol":state.symbol,"timestamp":state.timestamp,
            "decision_time":state.decision_time,"pit":state.point_in_time_available_at,
            "vector_version":state.vector_version,"feature_version":state.feature_version,
            "vector":json.dumps({"values":state.values,"availability":state.availability},default=str),
            "quality":json.dumps(state.data_quality,default=str),
            "provenance":json.dumps({"fingerprint":state.fingerprint,"state_id":state.fingerprint}),
        })

    def history(self,session:Session,symbol:str,limit:int=50):
        return session.execute(text("""
            SELECT state_id,timestamp,vector_version,feature_version,vector,data_quality
            FROM world.market_state_vectors WHERE symbol=:symbol
            ORDER BY timestamp DESC LIMIT :limit
        """),{"symbol":symbol,"limit":limit}).mappings().all()

    def get(self,session:Session,state_id:str):
        return session.execute(text("""
            SELECT state_id,symbol,timestamp,decision_time,point_in_time_available_at,
                   vector_version,feature_version,vector,market_state,data_quality,evidence,provenance
            FROM world.market_state_vectors WHERE state_id=:state_id
        """),{"state_id":state_id}).mappings().first()

    def at(self,session:Session,symbol:str,timestamp:datetime):
        return session.execute(text("""
            SELECT state_id,symbol,timestamp,decision_time,point_in_time_available_at,
                   vector_version,feature_version,vector,market_state,data_quality,evidence,provenance
            FROM world.market_state_vectors
            WHERE symbol=:symbol
            ORDER BY abs(EXTRACT(EPOCH FROM (timestamp - :timestamp))) LIMIT 1
        """),{"symbol":symbol,"timestamp":timestamp}).mappings().first()

    def compare(self,session:Session,symbol:str,left:datetime,right:datetime):
        rows=[
            self.at(session,symbol,left),
            self.at(session,symbol,right),
        ]
        if rows[0] is None or rows[1] is None:
            return None
        left_values=(rows[0]["vector"] or {}).get("values",rows[0]["vector"] or {})
        right_values=(rows[1]["vector"] or {}).get("values",rows[1]["vector"] or {})
        keys=sorted(set(left_values)|set(right_values))
        return {
            "symbol":symbol,
            "left_timestamp":rows[0]["timestamp"],
            "right_timestamp":rows[1]["timestamp"],
            "changed":{
                key:{"left":left_values.get(key),"right":right_values.get(key)}
                for key in keys if left_values.get(key)!=right_values.get(key)
            },
        }
