"""Keep tests isolated from recruiter data and persistent vector indexes."""

import atexit
import os
import shutil
import tempfile
from pathlib import Path


_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="talenthunt-tests-"))
os.environ["TALENTHUNT_DATA_DIR"] = str(_TEST_DATA_DIR)
os.environ["DB_PATH"] = str(_TEST_DATA_DIR / "talenthunt-test.db")


@atexit.register
def _remove_test_data() -> None:
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
