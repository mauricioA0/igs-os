"""Data converter and client factory used by every process that talks to Temporal.

The worker and the API must share the converter: when the worker encrypts payloads, the API
needs the same codec to start executions, send signals and read results.
"""

import base64
import dataclasses
from collections.abc import Sequence
from typing import Any

from temporalio.client import Client, Interceptor
from temporalio.converter import DataConverter

from igs_common.temporal.codec import EncryptionCodec

DEFAULT_NAMESPACE = "igs"


def make_data_converter(
    codec_key: str = "", *, codec_key_id: str = "k1", environment: str = "local"
) -> DataConverter:
    """``codec_key`` is a base64 AES-256 key. Empty disables encryption, except in production."""
    if not codec_key:
        if environment == "production":
            raise RuntimeError("a Temporal payload codec key is required in production")
        return DataConverter.default
    key = base64.b64decode(codec_key)
    if len(key) != 32:
        raise ValueError("codec key must be 32 bytes, base64-encoded")
    codec = EncryptionCodec({codec_key_id: key}, codec_key_id)
    return dataclasses.replace(DataConverter.default, payload_codec=codec)


async def connect_client(
    address: str,
    *,
    namespace: str = DEFAULT_NAMESPACE,
    data_converter: DataConverter | None = None,
    interceptors: Sequence[Interceptor] = (),
    **kwargs: Any,
) -> Client:
    return await Client.connect(
        address,
        namespace=namespace,
        data_converter=data_converter or DataConverter.default,
        interceptors=interceptors,
        **kwargs,
    )
