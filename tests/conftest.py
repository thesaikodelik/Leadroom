from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def no_market_model_calls():
    """Tests never wait on whatever Ollama is doing on this computer."""
    with patch("app.market._ask_model", return_value=None) as ask:
        yield ask


@pytest.fixture(autouse=True)
def no_list_page_downloads():
    """List pages found by a fake search are never fetched from the internet."""
    with patch("app.listings.fetch_page", return_value="") as fetch:
        yield fetch
