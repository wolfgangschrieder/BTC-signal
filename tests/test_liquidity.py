from datetime import datetime, timezone
from decimal import Decimal
from research_os.exchanges.bybit.orderbook import OrderBook
from research_os.features.liquidity import LiquidityEngine

def test_clusters_group_nearby_levels():
    book=OrderBook("BTCUSDT")
    book.restore_snapshot(
        [["100", "2"],["99.99","3"],["99.50","1"],["99.49","1"]],
        [["101","2"],["101.01","3"],["102","1"],["102.01","1"]],
        1,event_time_ms=1000)
    state=LiquidityEngine().build(book.state,100.5)
    assert state.valid
    assert state.strongest_bid is not None
    assert state.strongest_ask is not None
    assert state.strongest_bid.total_size==5
    assert state.strongest_ask.total_size==5

def test_invalid_book_produces_unavailable_state():
    book=OrderBook("BTCUSDT")
    state=LiquidityEngine().build(book.state,100)
    assert not state.valid
    assert state.strongest_bid is None
