from research_os.exchanges.bybit.orderbook import OrderBook
from research_os.data.models import QualityCode

def snapshot(ts=1000):
    return {
        "topic":"orderbook.50.BTCUSDT","type":"snapshot","ts":ts,
        "data":{"u":1,"seq":1,"b":[["100","2"]],"a":[["101","3"]]},
    }

def test_snapshot_and_delta():
    book=OrderBook("BTCUSDT")
    assert book.apply(snapshot()) is None
    assert book.state.valid
    assert book.state.bids[0].price==100
    quality=book.apply({
        "topic":"orderbook.50.BTCUSDT","type":"delta","ts":2000,
        "data":{"u":2,"seq":2,"b":[["100","4"]],"a":[]},
    })
    assert quality is None
    assert book.state.bids[0].size==4

def test_gap_invalidates_until_snapshot():
    book=OrderBook("BTCUSDT")
    book.apply(snapshot())
    quality=book.apply({
        "topic":"orderbook.50.BTCUSDT","type":"delta","ts":2000,
        "data":{"u":1,"seq":2,"b":[],"a":[]},
    })
    assert quality is not None and quality.code is QualityCode.DUPLICATE
    assert book.state.valid
    quality=book.apply({
        "topic":"orderbook.50.BTCUSDT","type":"delta","ts":3000,
        "data":{"u":3,"seq":0,"b":[],"a":[]},
    })
    assert quality is not None and quality.code is QualityCode.ORDERBOOK_GAP
    assert not book.state.valid
    assert book.apply(snapshot(4000)) is None
    assert book.state.valid

def test_stale_invalidates_book():
    book=OrderBook("BTCUSDT")
    book.apply(snapshot(1000))
    quality=book.mark_stale(7001,5000)
    assert quality is not None and quality.code is QualityCode.STALE
    assert not book.state.valid
