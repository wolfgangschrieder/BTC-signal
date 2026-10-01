from datetime import datetime, timedelta, timezone
from research_os.cross_market.models import CrossMarketObservation
from research_os.research.cross_market_dataset import CrossMarketDatasetBuilder

class Candle:
    def __init__(self,timestamp,close,high,low):
        self.timestamp=timestamp; self.close=close; self.high=high; self.low=low

def obs(asset,t,v):
    return CrossMarketObservation(asset,t,t,v,"test")

def test_dataset_is_pit_safe_and_chronological():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    observations=[obs("VIX",t-timedelta(days=30+i),100+i) for i in range(21)]
    observations.append(obs("VIX",t,200))
    late=CrossMarketObservation("VIX",t+timedelta(days=1),t+timedelta(days=2),999,"test")
    observations.append(late)
    candles=[Candle(t+timedelta(minutes=i),100+i,101+i,99+i) for i in range(0,61)]
    ds=CrossMarketDatasetBuilder().build("BTCUSDT",[t],observations,candles,horizons=(60,),min_samples=20,window_size=20)
    assert len(ds.rows)==1
    assert ds.rows[0].value==200
    assert ds.rows[0].normalized_available is True
    assert ds.rows[0].sample_size==20

def test_split_is_chronological():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    observations=[obs("VIX",t-timedelta(days=30+i),100+i) for i in range(21)]
    candles=[Candle(t+timedelta(minutes=i),100+i,101+i,99+i) for i in range(0,121)]
    times=[t,t+timedelta(minutes=60)]
    ds=CrossMarketDatasetBuilder().build("BTCUSDT",times,observations,candles,horizons=(60,),min_samples=20)
    train,test=CrossMarketDatasetBuilder.chronological_split(ds)
    assert all(a.timestamp<=b.timestamp for a,b in zip(train,train[1:]))
    assert (not test) or train[-1].timestamp<=test[0].timestamp
