from research_os.market.state_repository import MarketStateRepository

def test_state_repository_api():
    repo = MarketStateRepository()
    assert callable(repo.save)
    assert callable(repo.history)
    assert callable(repo.at)
