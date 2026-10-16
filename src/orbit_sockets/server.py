"""Bounded standalone WebSocket server built on the optional ``websockets`` extra."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from orbit_sockets import SocketClose, SocketHandler, SocketMessage
from orbit_sockets.errors import SocketClosedError, SocketError

_SUBPROTOCOL_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}\Z")
_MAX_ORIGINS = 64
_MAX_SUBPROTOCOLS = 64

if TYPE_CHECKING:
    from websockets.asyncio.server import Server, ServerConnection
    from websockets.http11 import Request, Response


@dataclass(frozen=True, slots=True)
class WebSocketServerSettings:
    """Validated listener and resource limits for one WebSocket endpoint."""

    host: str = "127.0.0.1"
    port: int = 8765
    path: str = "/ws"
    origins: tuple[str | None, ...] = (None,)
    subprotocols: tuple[str, ...] = ()
    max_connections: int = 256
    max_message_bytes: int = 262_144
    receive_queue_high: int = 4
    write_buffer_bytes: int = 32_768
    open_timeout_seconds: float = 10.0
    ping_interval_seconds: float | None = 20.0
    ping_timeout_seconds: float | None = 20.0
    close_timeout_seconds: float = 5.0
    shutdown_timeout_seconds: float = 10.0
    compression: str | None = None
    server_header: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.host, str)
            or not self.host
            or len(self.host) > 255
            or any(ord(character) < 33 or ord(character) > 126 for character in self.host)
        ):
            raise ValueError("host must be a non-empty bind address.")
        if (
            isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 0 <= self.port <= 65535
        ):
            raise ValueError("port must be between 0 and 65535.")
        if (
            not isinstance(self.path, str)
            or not self.path.startswith("/")
            or len(self.path) > 1_024
            or "?" in self.path
            or "#" in self.path
            or any(ord(character) < 33 or ord(character) > 126 for character in self.path)
        ):
            raise ValueError("path must be bounded printable ASCII without query or fragment.")
        if not isinstance(self.origins, tuple) or not isinstance(self.subprotocols, tuple):
            raise TypeError("origins and subprotocols must be immutable tuples.")
        if not self.origins:
            raise ValueError(
                "origins must explicitly allow one or more Origins, or None for no Origin."
            )
        if len(self.origins) > _MAX_ORIGINS:
            raise ValueError(f"origins cannot contain more than {_MAX_ORIGINS} entries.")
        if len(self.subprotocols) > _MAX_SUBPROTOCOLS:
            raise ValueError(f"subprotocols cannot contain more than {_MAX_SUBPROTOCOLS} entries.")
        origin_keys: set[tuple[str, str, int | None] | None] = set()
        for origin in self.origins:
            key = None if origin is None else _normalize_origin(origin)
            if key in origin_keys:
                raise ValueError("origins must be unique, including at most one no-Origin entry.")
            origin_keys.add(key)
        if any(
            not isinstance(protocol, str) or _SUBPROTOCOL_TOKEN.fullmatch(protocol) is None
            for protocol in self.subprotocols
        ):
            raise ValueError("subprotocols must be unique bounded HTTP token values.")
        if len(set(self.subprotocols)) != len(self.subprotocols):
            raise ValueError("subprotocols must be unique bounded HTTP token values.")
        if (
            isinstance(self.max_connections, bool)
            or not isinstance(self.max_connections, int)
            or not 1 <= self.max_connections <= 65_536
        ):
            raise ValueError("max_connections must be between 1 and 65536.")
        if (
            isinstance(self.max_message_bytes, bool)
            or not isinstance(self.max_message_bytes, int)
            or not 1 <= self.max_message_bytes <= 1_048_576
        ):
            raise ValueError("max_message_bytes must be between 1 byte and 1 MiB.")
        if (
            isinstance(self.receive_queue_high, bool)
            or not isinstance(self.receive_queue_high, int)
            or not 1 <= self.receive_queue_high <= 1024
        ):
            raise ValueError("receive_queue_high must be between 1 and 1024 frames.")
        if (
            isinstance(self.write_buffer_bytes, bool)
            or not isinstance(self.write_buffer_bytes, int)
            or not 1024 <= self.write_buffer_bytes <= 16_777_216
        ):
            raise ValueError("write_buffer_bytes must be between 1 KiB and 16 MiB.")
        for name in (
            "open_timeout_seconds",
            "close_timeout_seconds",
            "shutdown_timeout_seconds",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0.1 <= value <= 300
            ):
                raise ValueError(f"{name} must be between 0.1 and 300 seconds.")
        for name in ("ping_interval_seconds", "ping_timeout_seconds"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0.1 <= value <= 300
            ):
                raise ValueError(f"{name} must be None or between 0.1 and 300 seconds.")
        if self.compression not in {None, "deflate"}:
            raise ValueError("compression must be None or 'deflate'.")


def _normalize_origin(value: str) -> tuple[str, str, int | None]:
    """Validate one exact browser Origin and normalize its scheme, host, and effective port."""
    if (
        not isinstance(value, str)
        or not value.isascii()
        or len(value) > 512
        or any(ord(character) <= 32 or ord(character) >= 127 for character in value)
    ):
        raise ValueError("each allowed origin must be a bounded ASCII HTTP(S) origin.")
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError("each allowed origin must be a valid HTTP(S) origin.") from None
    if (
        scheme not in {"http", "https"}
        or not hostname
        or "*" in hostname
        or parsed.netloc.endswith(":")
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or not value.lower().startswith(f"{scheme}://")
    ):
        raise ValueError("each allowed origin must be an exact HTTP(S) origin without a path.")
    if port == (80 if scheme == "http" else 443):
        port = None
    return scheme, hostname.lower(), port


class WebSocketSession:
    """Adapt one websockets connection to Orbit's bounded session contract."""

    def __init__(self, connection: ServerConnection, max_message_bytes: int) -> None:
        self._connection = connection
        self._max_message_bytes = max_message_bytes
        self._close_lock = asyncio.Lock()
        self._closed = False

    async def receive(self) -> SocketMessage:
        """Receive one complete bounded message; cancellation is safe and propagates."""
        try:
            value = await self._connection.recv()
        except Exception as exc:
            from websockets.exceptions import ConnectionClosed

            if isinstance(exc, ConnectionClosed):
                self._closed = True
                raise SocketClosedError("WebSocket peer closed the session.") from None
            raise
        message = SocketMessage(value)
        if (
            len(value.encode("utf-8") if isinstance(value, str) else value)
            > self._max_message_bytes
        ):
            await self.close(SocketClose(1009, "message too large"))
            raise SocketError("Inbound WebSocket message exceeds the configured limit.")
        return message

    async def send(self, message: SocketMessage) -> None:
        """Send one message and await transport flow control."""
        if self._closed:
            raise SocketClosedError("WebSocket session is closed.")
        if not isinstance(message, SocketMessage):
            raise TypeError("message must be a SocketMessage.")
        size = len(message.data.encode("utf-8") if isinstance(message.data, str) else message.data)
        if size > self._max_message_bytes:
            raise SocketError("Outbound WebSocket message exceeds the configured limit.")
        try:
            await self._connection.send(message.data)
        except Exception as exc:
            from websockets.exceptions import ConnectionClosed

            if isinstance(exc, ConnectionClosed):
                self._closed = True
                raise SocketClosedError("WebSocket peer closed the session.") from None
            raise

    async def close(self, close: SocketClose | None = None) -> None:
        """Close once, completing the WebSocket close handshake where possible."""
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            try:
                selected = SocketClose() if close is None else close
                await self._connection.close(code=selected.code, reason=selected.reason)
            except Exception:
                raise SocketError("WebSocket close handshake failed.") from None


class WebSocketServer:
    """Own a bounded asyncio WebSocket listener and its accepted sessions."""

    def __init__(
        self,
        handler: SocketHandler,
        settings: WebSocketServerSettings | None = None,
    ) -> None:
        if not callable(handler):
            raise TypeError("handler must be callable.")
        self._handler = handler
        self._settings = WebSocketServerSettings() if settings is None else settings
        self._server: Server | None = None
        self._admission = asyncio.Semaphore(self._settings.max_connections)
        self._active: set[WebSocketSession] = set()
        self._handler_tasks: set[asyncio.Task[None]] = set()

    @property
    def address(self) -> tuple[str, int] | None:
        """Return the bound host and port after startup, including an ephemeral port."""
        if self._server is None or not self._server.sockets:
            return None
        host, port, *_ = self._server.sockets[0].getsockname()
        return str(host), int(port)

    @property
    def active_connections(self) -> int:
        """Return the current number of accepted sessions."""
        return len(self._active)

    async def start(self) -> None:
        """Bind and start accepting connections; repeated starts are rejected."""
        if self._server is not None:
            raise RuntimeError("WebSocket server is already started.")
        try:
            from websockets.asyncio.server import serve
            from websockets.typing import Origin, Subprotocol
        except ImportError:
            raise RuntimeError(
                "Install orbit-sockets[websockets] to use WebSocketServer."
            ) from None

        self._server = await serve(
            self._dispatch,
            self._settings.host,
            self._settings.port,
            origins=tuple(
                None if origin is None else Origin(origin) for origin in self._settings.origins
            ),
            subprotocols=tuple(Subprotocol(protocol) for protocol in self._settings.subprotocols),
            compression=self._settings.compression,
            open_timeout=self._settings.open_timeout_seconds,
            ping_interval=self._settings.ping_interval_seconds,
            ping_timeout=self._settings.ping_timeout_seconds,
            close_timeout=self._settings.close_timeout_seconds,
            max_size=self._settings.max_message_bytes,
            max_queue=self._settings.receive_queue_high,
            write_limit=self._settings.write_buffer_bytes,
            server_header=self._settings.server_header,
            process_request=self._check_path,
        )

    async def _check_path(self, connection: ServerConnection, request: Request) -> Response | None:
        if urlsplit(request.path).path == self._settings.path:
            return None
        return connection.respond(404, "Not Found\n")

    async def _dispatch(self, connection: ServerConnection) -> None:
        if self._server is None:
            await connection.close(code=1012, reason="server unavailable")
            return
        if self._admission.locked():
            await connection.close(code=1013, reason="server is at capacity")
            return
        await self._admission.acquire()
        task = asyncio.current_task()
        if task is not None:
            self._handler_tasks.add(task)
        session = WebSocketSession(connection, self._settings.max_message_bytes)
        self._active.add(session)
        try:
            await self._handler(session)
        except asyncio.CancelledError:
            await session.close(SocketClose(1001, "server shutting down"))
            raise
        except SocketClosedError:
            return
        except Exception:
            await session.close(SocketClose(1011, "handler failed"))
            logging.getLogger("orbit.sockets").error("WebSocket application handler failed.")
        finally:
            self._active.discard(session)
            if task is not None:
                self._handler_tasks.discard(task)
            self._admission.release()
            await session.close()

    async def close(self) -> None:
        """Stop accepting sessions and close active sessions with code 1001."""
        server = self._server
        if server is None:
            return
        self._server = None
        server.close(close_connections=False)
        await asyncio.gather(
            *(
                session.close(SocketClose(1001, "server shutting down"))
                for session in tuple(self._active)
            ),
            return_exceptions=True,
        )
        pending = tuple(self._handler_tasks)
        if pending:
            _, still_running = await asyncio.wait(
                pending, timeout=self._settings.shutdown_timeout_seconds
            )
            for task in still_running:
                task.cancel()
            if still_running:
                await asyncio.gather(*still_running, return_exceptions=True)
        await server.wait_closed()

    async def serve_forever(self) -> None:
        """Wait for shutdown after start; cancel or call ``close`` to stop the listener."""
        server = self._server
        if server is None:
            raise RuntimeError("WebSocket server is not started.")
        await server.serve_forever()

    async def __aenter__(self) -> WebSocketServer:
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.close()
