import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def service(tmp_path):
    from stapy_shop.db import Database
    from stapy_shop.service import ShopService

    db = Database(tmp_path / "test.db")
    svc = ShopService(db)
    yield svc
    db.close()
