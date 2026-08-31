"""L1-01d: fixture ProblemProvider SPI shape (write-provider drill)."""

from __future__ import annotations

import sys
from pathlib import Path

# 禁止 twin_id

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(_FIXTURES) not in sys.path:
    sys.path.insert(0, str(_FIXTURES))

from eval_stub_provider import ProblemProvider

_FORBIDDEN_HANDLE = "twin" + "_id"


def test_spi_shape() -> None:
    assert ProblemProvider.name
    assert ProblemProvider.name == "eval_stub"
    assert _FORBIDDEN_HANDLE not in vars(ProblemProvider)
    assert not hasattr(ProblemProvider, _FORBIDDEN_HANDLE)
    assert ProblemProvider().describe() == "eval_stub"


def main() -> int:
    test_spi_shape()
    print("ok  l101d_spi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
