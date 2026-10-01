from research_os.exchanges.bybit.normalizer import BybitNormalizer

def test_all_liquidation_items_are_normalized():
    events=BybitNormalizer.liquidations({"ts":1760000000100,"data":[{"T":1760000000000,"s":"BTCUSDT","S":"Buy","v":"2.5","p":"60000"},{"T":1760000000050,"s":"BTCUSDT","S":"Sell","v":"1.5","p":"60001"}]})
    assert len(events)==2
    assert {e.payload["side"] for e in events}=={"Buy","Sell"}
