"""Fork ``.postN`` versions must encode into a monotonic FnOS store version."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "fnos" / "store_version.sh"

posix_only = pytest.mark.skipif(os.name != "posix", reason="store_version.sh is a bash script")


def _store(version: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), version], capture_output=True, text=True)


def _triple(value: str) -> tuple[int, int, int]:
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


@posix_only
@pytest.mark.parametrize(
    ("pep440", "store"),
    [
        ("1.0.2b9.post1", "1.0.20901"),
        ("1.0.2b9.post10", "1.0.20910"),
        ("1.0.2b10.post2", "1.0.21002"),
        ("1.0.2.post1", "1.0.30001"),
        ("1.0.3b1.post1", "1.0.30101"),
    ],
)
def test_post_versions_append_two_digits(pep440: str, store: str) -> None:
    result = _store(pep440)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == store


@posix_only
def test_post_versions_sort_in_release_order() -> None:
    ordered = [
        "1.0.2b9.post1",
        "1.0.2b9.post9",
        "1.0.2b9.post10",
        "1.0.2b9.post99",
        "1.0.2b10.post1",
        "1.0.2b99.post99",
        "1.0.2.post1",
        "1.0.3b1.post1",
    ]
    encoded = [_triple(_store(v).stdout.strip()) for v in ordered]
    assert encoded == sorted(encoded)
    assert len(set(encoded)) == len(encoded)


@posix_only
def test_two_digit_codes_upgrade_released_one_digit_packages() -> None:
    # post1–post9 shipped with one-digit codes (1.0.2091–1.0.2099); every new code must sort above them.
    released = [(1, 0, 2090 + n) for n in range(1, 10)]
    for version in ("1.0.2b9.post10", "1.0.2b10.post1", "1.0.2.post1"):
        assert _triple(_store(version).stdout.strip()) > max(released)


@posix_only
@pytest.mark.parametrize("raw", ["1.0.2b9.post0", "1.0.2b9.post100", "1.0.2rc1.post1"])
def test_post_versions_reject_unencodable(raw: str) -> None:
    assert _store(raw).returncode != 0
