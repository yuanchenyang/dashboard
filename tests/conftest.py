import pytest

import dashboard


@pytest.fixture(autouse=True)
def clear_dashboard_cache():
    dashboard.cache.clear()
    yield
    dashboard.cache.clear()
