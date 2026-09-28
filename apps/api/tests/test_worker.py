"""Worker dispatch routing — unit-level, no live job claim/DB loop here."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.worker import dispatch_inspection


def test_dispatch_rejects_unknown_product_key(tmp_path: Path) -> None:
    dummy = tmp_path / "file.bin"
    dummy.write_bytes(b"x")
    with pytest.raises(ValueError):
        dispatch_inspection("unknown_product", dummy)
