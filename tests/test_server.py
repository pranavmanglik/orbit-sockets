import asyncio

import pytest

from orbit_sockets import (
    SocketMessage,
    WebSocketServer,
    WebSocketServerSettings,
)


def test_settings_reject_unsafe_or_unbounded_values() -> None:
    with pytest.raises(ValueError):
        WebSocketServerSettings(origins=())
    with pytest.raises(ValueError):
        WebSocketServerSettings(max_message_bytes=1_048_577)
    with pytest.raises(ValueError):
        WebSocketServerSettings(max_connections=0)
    with pytest.raises(ValueError):
        WebSocketServerSettings(origins=("https://app.example/path",))
    with pytest.raises(TypeError):
        WebSocketServerSettings(origins=["https://app.example"])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "settings",
    [
        {"origins": ("https://app.example", "HTTPS://APP.EXAMPLE:443")},
        {"origins": ("https://*.example",)},
        {"origins": ("https://app.example:",)},
        {"origins": ("https://app.example",) * 65},
        {"subprotocols": ("chat", "chat")},
        {"subprotocols": ("chat\r\nInjected: value",)},
        {"subprotocols": ("p" * 129,)},
        {"subprotocols": ("chat",) * 65},
        {"path": "/ws\nInjected"},
    ],
)
def test_settings_reject_ambiguous_or_unbounded_origins_and_protocols(
    settings: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        WebSocketServerSettings(**settings)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_server_round_trip_and_graceful_shutdown() -> None:
    from websockets.asyncio.client import connect

    received = asyncio.Event()

    async def handler(session: object) -> None:
        message = await session.receive()  # type: ignore[attr-defined]
        assert message == SocketMessage("hello")
        await session.send(SocketMessage("world"))  # type: ignore[attr-defined]
        received.set()

    server = WebSocketServer(
        handler, WebSocketServerSettings(host="127.0.0.1", port=0, origins=(None,))
    )
    await server.start()
    try:
        address = server.address
        assert address is not None
        async with connect(f"ws://{address[0]}:{address[1]}/ws") as client:
            await client.send("hello")
            assert await client.recv() == "world"
        await asyncio.wait_for(received.wait(), timeout=2)
    finally:
        await server.close()
    assert server.address is None


@pytest.mark.asyncio
async def test_server_rejects_unconfigured_origin() -> None:
    from websockets.asyncio.client import connect
    from websockets.exceptions import InvalidStatus
    from websockets.typing import Origin

    async def handler(session: object) -> None:
        await session.receive()  # type: ignore[attr-defined]

    server = WebSocketServer(
        handler,
        WebSocketServerSettings(host="127.0.0.1", port=0, origins=("https://allowed.example",)),
    )
    await server.start()
    try:
        address = server.address
        assert address is not None
        with pytest.raises(InvalidStatus):
            async with connect(
                f"ws://{address[0]}:{address[1]}/ws",
                origin=Origin("https://untrusted.example"),
            ):
                pass
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_server_rejects_unknown_path_before_upgrade() -> None:
    from websockets.asyncio.client import connect
    from websockets.exceptions import InvalidStatus

    async def handler(session: object) -> None:
        await session.receive()  # type: ignore[attr-defined]

    server = WebSocketServer(handler, WebSocketServerSettings(port=0))
    await server.start()
    try:
        address = server.address
        assert address is not None
        with pytest.raises(InvalidStatus):
            async with connect(f"ws://{address[0]}:{address[1]}/unknown"):
                pass
    finally:
        await server.close()
