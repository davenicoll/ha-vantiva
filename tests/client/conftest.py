"""Shared test setup for the client library tests.

aioresponses 0.7.9 is not fully compatible with aiohttp 3.14 (the version Home Assistant ships):

* it builds ``ClientResponse`` objects without the now-mandatory ``stream_writer`` argument;
* bodies above 64 KiB (``device-modal.lp`` is ~280 KB) make its fake protocol call
  ``pause_reading()`` on a handler without a parser, which asserts.

Until aioresponses catches up, patch both inside its module only.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import aioresponses.core
from aiohttp import ClientResponse
from aiohttp.client_proto import ResponseHandler
from aiohttp.streams import StreamReader


class _NullStreamWriter:
    output_size = 0


if "stream_writer" in inspect.signature(ClientResponse.__init__).parameters:

    class _CompatClientResponse(ClientResponse):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("stream_writer", _NullStreamWriter())
            super().__init__(*args, **kwargs)

    aioresponses.core.ClientResponse = _CompatClientResponse  # type: ignore[misc]


def _stream_reader_factory(loop: asyncio.AbstractEventLoop | None = None) -> StreamReader:
    protocol = ResponseHandler(loop=loop or asyncio.get_running_loop())
    return StreamReader(protocol, limit=2**26, loop=loop or asyncio.get_running_loop())


aioresponses.core.stream_reader_factory = _stream_reader_factory  # type: ignore[assignment]
