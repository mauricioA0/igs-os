"""ISO-8601 durations as used in flow documents (PT10S, P2D, P1DT12H…)."""

import re
from datetime import timedelta

_RE = re.compile(
    r"^P(?:(?P<w>\d+)W)?(?:(?P<d>\d+)D)?"
    r"(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+(?:\.\d+)?)S)?)?$"
)


def parse_duration(value: str) -> timedelta:
    m = _RE.match(value)
    if not m or value in ("P", "PT"):
        raise ValueError(f"invalid ISO-8601 duration: {value!r}")
    g = {k: float(v) if v else 0.0 for k, v in m.groupdict().items()}
    return timedelta(weeks=g["w"], days=g["d"], hours=g["h"], minutes=g["m"], seconds=g["s"])
