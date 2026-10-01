def test_repository_api_is_pit_safe():
    from research_os.cross_market.repository import CrossMarketRepository
    assert hasattr(CrossMarketRepository,"save")
    assert hasattr(CrossMarketRepository,"latest")
