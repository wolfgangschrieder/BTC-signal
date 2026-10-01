from datetime import datetime, timezone
from research_os.pipeline.live import LiveSignalService

def test_live_service_uses_only_public_read_topics():
    s=LiveSignalService()
    assert set(s.websocket._topics)=={"kline.1.BTCUSDT","tickers.BTCUSDT","orderbook.50.BTCUSDT"}

def test_live_atr_is_derived_from_true_ohlc():
    s=LiveSignalService()
    for x in range(100,107):
        s.closes.append(float(x))
        s.highs.append(float(x)+1)
        s.lows.append(float(x)-1)
    snapshot=s.features.build(
        "BTCUSDT",datetime(2026,1,1,tzinfo=timezone.utc),
        list(s.closes),highs=list(s.highs),lows=list(s.lows),
    )
    assert s._atr_from_features(snapshot) is not None
