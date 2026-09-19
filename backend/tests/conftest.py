import os
from pathlib import Path

import pytest


TEST_DB = Path(__file__).parent / "test.db"
TEST_UPLOADS = Path(__file__).parent / "uploads"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["UPLOAD_DIR"] = str(TEST_UPLOADS)
os.environ["ADMIN_PASSWORD"] = "test-admin-password"

from fastapi.testclient import TestClient  # noqa: E402

from app.core import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)
    if TEST_UPLOADS.exists():
        for path in TEST_UPLOADS.iterdir():
            path.unlink()
