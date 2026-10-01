from decimal import Decimal

from research_os.data.models import QualityCode
from research_os.exchanges.bybit.orderbook import OrderBook


def snapshot() -> dict:
    return {
        "topic": "orderbook.50.BTCUSDT",
        "type": "snapshot",
        "ts": 1000,
        "data": {
            "s": "BTCUSDT",
            "u": 10,
            "seq": 100,
            "b": [["100", "2"], ["99", "1"]],
            "a": [["101", "3"], ["102", "1"]],
        },
    }


def delta(update_id: int, *, seq: int = 101) -> dict:
    return {
        "topic": "orderbook.50.BTCUSDT",
        "type": "delta",
        "ts": 1100,
        "data": {
            "s": "BTCUSDT",
            "u": update_id,
            "seq": seq,
            "b": [["100", "1.5"]],
            "a": [["101", "0"]],
        },
    }


def test_snapshot_builds_valid_book():
    book = OrderBook("BTCUSDT")
    assert book.apply(snapshot()) is None
    state = book.state
    assert state.valid is True
    assert state.bids[0].price == Decimal("100")
    assert state.asks[0].price == Decimal("101")


def test_delta_updates_and_removes_levels():
    book = OrderBook("BTCUSDT")
    book.apply(snapshot())
    assert book.apply(delta(11)) is None
    assert book.state.bids[0].size == Decimal("1.5")
    assert book.state.asks[0].price == Decimal("102")


def test_delta_before_snapshot_invalidates_book():
    book = OrderBook("BTCUSDT")
    quality = book.apply(delta(11))
    assert quality is not None
    assert quality.code == QualityCode.ORDERBOOK_GAP
    assert book.state.valid is False


def test_duplicate_update_is_reported():
    book = OrderBook("BTCUSDT")
    book.apply(snapshot())
    quality = book.apply(delta(10))
    assert quality is not None
    assert quality.code == QualityCode.DUPLICATE


def test_crossed_book_invalidates():
    book = OrderBook("BTCUSDT")
    book.apply(snapshot())
    quality = book.apply(
        {
            "topic": "orderbook.50.BTCUSDT",
            "type": "delta",
            "ts": 1200,
            "data": {
                "u": 11,
                "seq": 101,
                "b": [["102", "1"]],
                "a": [],
            },
        }
    )
    assert quality is not None
    assert quality.code == QualityCode.IMPOSSIBLE_VALUE
    assert book.state.valid is False
