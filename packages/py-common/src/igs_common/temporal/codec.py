"""Payload codec: zlib compression + AES-256-GCM encryption for everything sent to Temporal.

Temporal history then holds only ciphertext; the key lives in Secret Manager and only workers
(and the API, to decode for the panel) have it. The key id travels in the payload metadata so
keys can be rotated without breaking running executions.
"""

import os
import zlib
from collections.abc import Mapping, Sequence

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from temporalio.api.common.v1 import Payload
from temporalio.converter import PayloadCodec

ENCODING = b"binary/igs-zlib-aesgcm"
_NONCE_BYTES = 12


class EncryptionCodec(PayloadCodec):
    def __init__(self, keys: Mapping[str, bytes], active_key_id: str) -> None:
        if active_key_id not in keys:
            raise ValueError(f"active key {active_key_id!r} not in keys")
        self._ciphers = {kid: AESGCM(key) for kid, key in keys.items()}
        self._active = active_key_id

    async def encode(self, payloads: Sequence[Payload]) -> list[Payload]:
        cipher = self._ciphers[self._active]
        out: list[Payload] = []
        for p in payloads:
            nonce = os.urandom(_NONCE_BYTES)
            plain = zlib.compress(p.SerializeToString())
            # The key id is bound as associated data, so a payload can't be relabeled.
            data = nonce + cipher.encrypt(nonce, plain, self._active.encode())
            out.append(
                Payload(
                    metadata={"encoding": ENCODING, "encryption-key-id": self._active.encode()},
                    data=data,
                )
            )
        return out

    async def decode(self, payloads: Sequence[Payload]) -> list[Payload]:
        out: list[Payload] = []
        for p in payloads:
            if p.metadata.get("encoding") != ENCODING:
                out.append(p)  # written before encryption was enabled
                continue
            kid = p.metadata["encryption-key-id"].decode()
            cipher = self._ciphers.get(kid)
            if cipher is None:
                raise ValueError(f"unknown encryption key id {kid!r}")
            nonce, ct = p.data[:_NONCE_BYTES], p.data[_NONCE_BYTES:]
            decoded = Payload()
            decoded.ParseFromString(zlib.decompress(cipher.decrypt(nonce, ct, kid.encode())))
            out.append(decoded)
        return out
