from research_os.market.state_repository import MarketStateRepository

def test_repository_exposes_persistence_and_comparison_api():
    repo=MarketStateRepository()
    assert hasattr(repo,"save")
    assert hasattr(repo,"get")
    assert hasattr(repo,"history")
    assert hasattr(repo,"at")
    assert hasattr(repo,"compare")
