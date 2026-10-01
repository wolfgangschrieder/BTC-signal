from datetime import datetime,timedelta,timezone
from research_os.research.replay import ReplayCandle,ReplayEngine

def candles(prices):
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    return [ReplayCandle(t+timedelta(minutes=i),p,p+0.2,p-0.2,p,1,t+timedelta(minutes=i)) for i,p in enumerate(prices)]

def test_replay_is_deterministic():
    data=candles([100,100.1,100.2,100.3,100.4,100.5,101,101.2,101.4,101.6])
    e=ReplayEngine()
    a=e.run("BTCUSDT",data,"fixture-v1"); b=e.run("BTCUSDT",data,"fixture-v1")
    assert a==b

def test_replay_rejects_future_information():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    data=[ReplayCandle(t+i*timedelta(minutes=1),100,101,99,100,1,t+(i+1)*timedelta(minutes=1)) for i in range(6)]
    try: ReplayEngine().run("BTCUSDT",data)
    except ValueError as exc: assert "availability" in str(exc)
    else: raise AssertionError("future PIT must be rejected")
