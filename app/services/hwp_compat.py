"""Diagnostics and validation for pyhwp (import name: hwp5) used for legacy .hwp conversion."""

from __future__ import annotations

import logging
import sys
from importlib.util import find_spec
from typing import Any

logger = logging.getLogger(__name__)


def describe_pyhwp_stack() -> dict[str, Any]:
    """Return structured status for /healthz and logs; does not raise."""
    out: dict[str, Any] = {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "checks": {},
    }

    def _safe_step(name: str, fn: Any) -> None:
        try:
            fn()
            out["checks"][name] = "ok"
        except Exception as e:  # noqa: BLE001 — diagnostic aggregation
            out["checks"][name] = f"error: {e!s}"

    def _needs_lxml() -> None:
        import lxml.etree  # noqa: F401

    def _needs_olefile() -> None:
        import olefile  # noqa: F401

    def _needs_cryptography() -> None:
        import cryptography  # noqa: F401

    def _needs_hwp5() -> None:
        import hwp5  # noqa: F401

    def _needs_odt_transform() -> None:
        from hwp5.cli import init_with_environ
        from hwp5.hwp5odt import ODTTransform

        init_with_environ()
        ODTTransform()

    # Order matters for readable failures.
    def _needs_six() -> None:
        import six  # noqa: F401

    for label, fn in (
        ("lxml", _needs_lxml),
        ("olefile", _needs_olefile),
        ("cryptography", _needs_cryptography),
        ("six", _needs_six),
        ("hwp5", _needs_hwp5),
        ("pyhwp_odt_transform", _needs_odt_transform),
    ):
        _safe_step(label, fn)

    checks = out["checks"]
    out["pyhwp_ready"] = all(v == "ok" for v in checks.values())
    return out


def assert_pyhwp_import_chain() -> None:
    """Used before HWP conversion. Raises RuntimeError with a precise cause."""
    if find_spec("hwp5") is None:
        raise RuntimeError(
            "패키지 'pyhwp'가 현재 파이썬 환경에 설치되어 있지 않습니다. "
            f"executable={sys.executable}. pip install pyhwp==0.1b15 또는 requirements.txt 재설치 후 확인하세요."
        )

    try:
        import lxml.etree  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "pyhwp가 의존하는 lxml 로드 실패입니다. Dockerfile/requirements와 동일 버전으로 lxml 설치가 필요합니다. "
            f"원인: {e!s}"
        ) from e

    try:
        import olefile  # noqa: F401
    except ImportError as e:
        raise RuntimeError(f"pyhwp 의존성 olefile 로드 실패: {e!s}") from e

    try:
        import cryptography  # noqa: F401
    except ImportError as e:
        raise RuntimeError(f"pyhwp 의존성 cryptography 로드 실패: {e!s}") from e

    try:
        import six  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            f"pyhwp ODT 경로에 필요한 six 로드 실패: {e!s}. requirements.txt의 six 항목을 설치하세요."
        ) from e

    try:
        import hwp5  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "hwp5 모듈 import 실패 (pip 패키지 이름은 pyhwp). "
            f"executable={sys.executable}, 원인: {e!s}"
        ) from e


def log_pyhwp_stack_at_startup() -> None:
    status = describe_pyhwp_stack()
    if status.get("pyhwp_ready"):
        logger.info("pyhwp stack ready: %s", status["checks"])
    else:
        logger.warning("pyhwp stack not fully ready — .hwp conversion may fail: %s", status)
