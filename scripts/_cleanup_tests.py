"""One-off maintenance helper: normalise second-user setup in the tests.

Every "register a second account" block looks like

    client.post("/api/auth/logout", headers=JSON)
    register(client, email="other@wize.local")

Registration signs the new user in, so this is replaced with the shared
``switch_user`` helper from ``tests/conftest.py``.

Usage:  python scripts/_cleanup_tests.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = PROJECT_ROOT / "tests"

REGISTER_RE = re.compile(r"^\s*register\(client.*\)\s*$")
LOGIN_RE = re.compile(r"^\s*login\(client.*\)\s*$")
LOGOUT_RE = re.compile(r"^\s*client\.post\(\"/api/auth/logout\".*\)\s*$")


def strip_redundant_logins(path: Path) -> int:
    """Remove a `login()` that directly follows `register()` (register signs in)."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    output: list[str] = []
    removed = 0
    previous_was_register = False
    for line in lines:
        if LOGIN_RE.match(line) and previous_was_register:
            removed += 1
            previous_was_register = False
            continue
        output.append(line)
        previous_was_register = bool(REGISTER_RE.match(line))
    if removed:
        path.write_text("".join(output), encoding="utf-8")
    return removed


def merge_logout_register(path: Path) -> int:
    """Collapse `logout` + `register(email=...)` into `switch_user(...)`."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    output: list[str] = []
    merged = 0
    index = 0
    while index < len(lines):
        if (LOGOUT_RE.match(lines[index])
                and index + 1 < len(lines)
                and REGISTER_RE.match(lines[index + 1])
                and "email=" in lines[index + 1]):
            indent = len(lines[index]) - len(lines[index].lstrip())
            email = re.search(r'email="([^"]+)"', lines[index + 1]).group(1)
            output.append(" " * indent + f"switch_user(client, \"{email}\")\n")
            index += 2
            merged += 1
            continue
        output.append(lines[index])
        index += 1
    if merged:
        path.write_text("".join(output), encoding="utf-8")
    return merged


def main() -> int:
    total_removed = total_merged = 0
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        removed = strip_redundant_logins(path)
        merged = merge_logout_register(path)
        total_removed += removed
        total_merged += merged
        print(f"{path.name}: removed {removed} login(), merged {merged} logout()+register()")
    print(f"Totals: removed={total_removed} merged={total_merged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())