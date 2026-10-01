from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import create_engine, text
from research_os.execution.service import ExecutionRecord

class ExecutionRepository:
    """Persistent execution state. Signal outcome statistics never depend on this repository."""
    def __init__(self,database_url: str):
        self.engine=create_engine(database_url,pool_pre_ping=True)

    def save(self, record: ExecutionRecord) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO execution.orders
                (client_order_id,signal_id,symbol,side,order_type,quantity,limit_price,stop_loss,take_profit,status,
                 exchange_order_id,reason,created_at,updated_at)
                VALUES (:client_order_id,:signal_id,:symbol,:side,:order_type,:quantity,:limit_price,:stop_loss,:take_profit,
                        :status,:exchange_order_id,:reason,:created_at,:updated_at)
                ON CONFLICT (client_order_id) DO UPDATE SET
                  status=EXCLUDED.status, exchange_order_id=EXCLUDED.exchange_order_id,
                  reason=EXCLUDED.reason, updated_at=EXCLUDED.updated_at
            """),{
                "client_order_id":record.client_order_id,"signal_id":record.signal_id,"symbol":record.intent.symbol,
                "side":record.intent.side.value,"order_type":record.intent.order_type.value,"quantity":record.intent.quantity,
                "limit_price":record.intent.limit_price,"stop_loss":record.intent.stop_loss,"take_profit":record.intent.take_profit,
                "status":record.status.value,"exchange_order_id":record.exchange_order_id,"reason":record.reason,
                "created_at":record.created_at,"updated_at":record.updated_at,
            })

    def append_event(self,client_order_id: str,signal_id: str,event_type: str,to_status: str,
                     event_time: datetime,from_status: str|None=None,reason: str|None=None,
                     exchange_order_id: str|None=None) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO execution.events
                (client_order_id,signal_id,event_type,from_status,to_status,reason,exchange_order_id,event_time)
                VALUES (:client_order_id,:signal_id,:event_type,:from_status,:to_status,:reason,:exchange_order_id,:event_time)
            """),locals())
