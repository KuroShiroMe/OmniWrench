"""Einfacher Versionsvergleich (SemVer-ähnlich, z. B. "1.2.3", "v1.4", "2.0.0-beta1")."""

from __future__ import annotations

import re

_PART = re.compile(r"(\d+)")


def parse_version(text: str) -> tuple:
    text = (text or "0").strip().lstrip("vV")
    main, _, pre = text.partition("-")
    nums = [int(p) for p in _PART.findall(main)] or [0]
    while len(nums) < 3:
        nums.append(0)
    # Vorabversionen (mit "-...") sind kleiner als die finale Version
    return (*nums, 0 if pre else 1, pre)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)
