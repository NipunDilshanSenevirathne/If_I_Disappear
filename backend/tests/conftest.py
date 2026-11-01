import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True, scope="session")
def _isolated_data(tmp_path_factory):
    data = tmp_path_factory.mktemp("iid-data")
    os.environ["IID_DATA_DIR"] = str(data)
    os.environ.pop("MODEL_API_KEY", None)
    os.environ["IID_MODE"] = "judge"
    os.environ["IID_RATE_LIMIT_SCALE"] = "100"
    yield data


@pytest.fixture(autouse=True)
def _closed_breakers():
    """The circuit breaker is shared by the whole process, so one test's failures can't be left
    open for the next."""
    yield
    from app.meta.client import reset_breakers

    reset_breakers()
