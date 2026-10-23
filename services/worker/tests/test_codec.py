import base64
import os

import pytest
from cryptography.exceptions import InvalidTag
from temporalio.api.common.v1 import Payload
from temporalio.converter import DataConverter

from igs_common.temporal import ENCODING, EncryptionCodec
from igs_worker.settings import WorkerSettings
from igs_worker.worker import data_converter


def _payload(text: str) -> Payload:
    return Payload(metadata={"encoding": b"json/plain"}, data=text.encode())


async def test_roundtrip_hides_plaintext() -> None:
    codec = EncryptionCodec({"k1": os.urandom(32)}, "k1")
    [enc] = await codec.encode([_payload('{"coach":"Dana Whitfield"}')])
    assert enc.metadata["encoding"] == ENCODING
    assert b"Whitfield" not in enc.data
    [dec] = await codec.decode([enc])
    assert dec.data == b'{"coach":"Dana Whitfield"}'


async def test_rotation_reads_old_key_writes_new() -> None:
    k1, k2 = os.urandom(32), os.urandom(32)
    [old] = await EncryptionCodec({"k1": k1}, "k1").encode([_payload("x")])
    rotated = EncryptionCodec({"k1": k1, "k2": k2}, "k2")
    assert (await rotated.decode([old]))[0].data == b"x"
    [new] = await rotated.encode([_payload("y")])
    assert new.metadata["encryption-key-id"] == b"k2"


async def test_tampering_and_wrong_key_fail() -> None:
    [enc] = await EncryptionCodec({"k1": os.urandom(32)}, "k1").encode([_payload("x")])
    with pytest.raises(InvalidTag):
        await EncryptionCodec({"k1": os.urandom(32)}, "k1").decode([enc])
    enc.metadata["encryption-key-id"] = b"k9"
    with pytest.raises(ValueError, match="unknown encryption key"):
        await EncryptionCodec({"k1": os.urandom(32)}, "k1").decode([enc])


async def test_unencrypted_payloads_pass_through() -> None:
    codec = EncryptionCodec({"k1": os.urandom(32)}, "k1")
    assert (await codec.decode([_payload("legacy")]))[0].data == b"legacy"


def test_converter_requires_key_in_production() -> None:
    assert data_converter(WorkerSettings(codec_key="")) is DataConverter.default
    with pytest.raises(RuntimeError):
        data_converter(WorkerSettings(codec_key="", environment="production"))
    key = base64.b64encode(os.urandom(32)).decode()
    assert data_converter(WorkerSettings(codec_key=key)).payload_codec is not None


def test_worker_and_api_share_the_shared_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("IGS_TEMPORAL_CODEC_KEY", key)
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "igs")
    settings = WorkerSettings()
    assert settings.codec_key == key and settings.temporal_namespace == "igs"


def test_default_namespace_is_igs() -> None:
    assert WorkerSettings().temporal_namespace == "igs"
