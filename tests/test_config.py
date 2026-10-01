import os
from research_os.core.config import Settings

def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    settings = Settings()
    assert settings.signal_min_probability == 0.70
    assert settings.environment == "development"
