import random
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from igs_common.domain.approvals import canonical_json, payload_hash, verify_payload
from igs_common.domain.enums import ItemStatus

PAYLOAD = {
    "to": "coach@lakeshore.example",
    "trip_id": UUID("8f14e45f-ceea-467a-9c3e-1b2c3d4e5f60"),
    "amount": Decimal("2890.00"),
    "items": [1, 2, 3],
    "status": ItemStatus.CONFIRMED,
    "send_at": datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
    "start": date(2027, 3, 7),
}


def test_hash_is_prefixed_and_stable():
    h = payload_hash("send_message", PAYLOAD)
    assert h.startswith("sha256:") and len(h) == len("sha256:") + 64
    assert h == payload_hash("send_message", dict(reversed(PAYLOAD.items())))


@pytest.mark.parametrize("seed", range(50))
def test_key_order_never_matters(seed):
    items = list(PAYLOAD.items())
    random.Random(seed)  # noqa: S311 - seeded test data.shuffle(items)
    assert payload_hash("a", dict(items)) == payload_hash("a", PAYLOAD)


def test_any_change_changes_hash():
    base = payload_hash("send_message", PAYLOAD)
    assert payload_hash("send_message", PAYLOAD | {"to": "other@x.example"}) != base
    assert payload_hash("send_message", PAYLOAD | {"items": [1, 3, 2]}) != base
    assert payload_hash("cancel_trip", PAYLOAD) != base


def test_equivalent_scalars_normalize():
    assert canonical_json({"x": Decimal("2890.00")}) == canonical_json({"x": Decimal("2890")})
    assert canonical_json({"x": 3.0}) == canonical_json({"x": 3})
    other_tz = datetime(2026, 11, 1, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert canonical_json({"t": other_tz}) == canonical_json({"t": PAYLOAD["send_at"]})


def test_sets_are_order_independent():
    assert canonical_json({"s": {"b", "a"}}) == canonical_json({"s": {"a", "b"}})


def test_verify():
    h = payload_hash("send_message", PAYLOAD)
    assert verify_payload(h, "send_message", PAYLOAD)
    assert not verify_payload(h, "send_message", PAYLOAD | {"amount": Decimal("1")})


@pytest.mark.parametrize(
    "bad",
    [float("nan"), float("inf"), Decimal("NaN"), datetime(2026, 1, 1), object()],
)
def test_rejects_ambiguous_values(bad):
    with pytest.raises((ValueError, TypeError)):
        payload_hash("x", {"v": bad})


def test_rejects_colliding_keys():
    with pytest.raises(ValueError):
        canonical_json({1: "a", "1": "b"})


def test_action_required():
    with pytest.raises(ValueError):
        payload_hash("", {})
