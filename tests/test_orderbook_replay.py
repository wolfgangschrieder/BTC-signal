from datetime import datetime, timezone, timedelta
from research_os.research.orderbook_replay import HistoricalOrderBookEvent, replay_to

def test_orderbook_replay_respects_pit():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    snap={"topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":1000,
          "data":{"u":1,"seq":1,"b":[["99","2"]],"a":[["101","2"]]}}
    future={"topic":"orderbook.50.BTCUSDT","type":"delta","ts":3000,
            "data":{"u":2,"seq":2,"b":[["99","9"]],"a":[]}}
    events=[
      HistoricalOrderBookEvent(t,t,snap),
      HistoricalOrderBookEvent(t+timedelta(seconds=2),t+timedelta(seconds=2),future),
    ]
    state=replay_to(events,t+timedelta(seconds=1),"BTCUSDT")
    assert state is not None
    assert str(state.bids[0].size)=="2"

def test_orderbook_replay_rejects_future_pit():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    snap={"topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":1000,
          "data":{"u":1,"seq":1,"b":[["99","2"]],"a":[["101","2"]]}}
    delayed=HistoricalOrderBookEvent(t,t+timedelta(seconds=2),snap)
    assert replay_to([delayed],t,"BTCUSDT") is None
