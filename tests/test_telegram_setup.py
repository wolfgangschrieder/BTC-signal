import importlib.util
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location(
    "telegram_setup", Path(__file__).parents[1] / "deploy/configure-telegram.py"
)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_save_preserves_database_and_disables_delivery(tmp_path):
    path = tmp_path / ".env"
    path.write_text("POSTGRES_PASSWORD=existing\nTELEGRAM_BOT_TOKEN=old\nSIGNAL_EMISSION_ENABLED=true\n")
    setup.save_settings(path, "123:placeholder", "42")
    assert path.read_text() == (
        "POSTGRES_PASSWORD=existing\nTELEGRAM_BOT_TOKEN=123:placeholder\n"
        "TELEGRAM_CHAT_ID=42\nSIGNAL_EMISSION_ENABLED=false\n"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_network_error_does_not_expose_token():
    with (
        patch.object(setup.urllib.request, "urlopen", side_effect=ValueError("SECRET_URL")),
        pytest.raises(setup.SetupError) as error,
    ):
        setup.api("123:placeholder", "getMe")
    assert "SECRET_URL" not in str(error.value)
    assert "placeholder" not in str(error.value)


def test_discovery_only_includes_private_start():
    updates = [
        {"message": {"text": "/start", "chat": {"id": 42, "type": "private"}}},
        {"message": {"text": "hello", "chat": {"id": 43, "type": "private"}}},
        {"message": {"text": "/start", "chat": {"id": -44, "type": "group"}}},
    ]
    assert list(setup.private_chats(updates)) == ["42"]


def test_symlink_not_overwritten(tmp_path):
    target = tmp_path / "target"
    target.write_text("unchanged")
    path = tmp_path / ".env"
    path.symlink_to(target)
    with pytest.raises(setup.SetupError):
        setup.save_settings(path, "123:placeholder", "42")
    assert target.read_text() == "unchanged"
