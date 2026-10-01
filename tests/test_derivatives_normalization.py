from datetime import datetime, timezone
from research_os.exchanges.bybit.normalizer import BybitNormalizer

def test_ticker_normalizes_funding_and_open_interest():
    event=BybitNormalizer.ticker(
        {"data":{"symbol":"BTCUSDT","lastPrice":"100000","bid1Price":"99999","ask1Price":"100001","fundingRate":"0.0001","openInterest":"1234","nextFundingTime":"1760000000000"},"ts":1760000000000},
        datetime.now(timezone.utc),
    )
    assert event.payload["funding_rate"] == "0.0001"
    assert event.payload["open_interest"] == "1234"
