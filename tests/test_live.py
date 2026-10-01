from research_os.pipeline.live import LiveSignalService

def test_live_service_uses_only_public_read_topics():
 s=LiveSignalService()
 assert set(s.websocket._topics)=={"kline.1.BTCUSDT","tickers.BTCUSDT","orderbook.50.BTCUSDT"}

def test_live_close_window_and_volatility_proxy():
 s=LiveSignalService()
 for x in range(100,107): s.closes.append(x)
 assert len(s.closes)==7 and s._range_proxy()==1
