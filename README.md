# Orbit Sockets

`orbit-sockets` defines bounded, provider-neutral async WebSocket session contracts and a Python
standalone listener for Orbit applications. It does not add a framework or a second ASGI server.
Configure the application or deployment to select one implementation explicitly.

The public contract bounds each text or binary message to 1 MiB and close reasons to 123 UTF-8
bytes. Implementations must apply bounded receive buffering, honor transport flow control, propagate
cancellation, perform an idempotent close handshake, and avoid logging payloads or provider exception
text. A successful send indicates transport acceptance, not application-level delivery.

`orbit-realtime` remains the separately installable Server-Sent Events package. WebTransport uses a
separate package because HTTP/3 over QUIC has distinct stream, datagram, TLS, ingress, and lifecycle
requirements; it is not treated as a WebSocket mode. Runtime availability and maturity are stated by
each implementation package.

WebRTC peer connections are implemented separately in `orbit-webrtc` (Python) and
`orbit-webrtc-go` (Go); their signaling contract and ICE/media lifecycle are different from a
WebSocket listener.

## WebSocket implementations

The Python listener in `orbit-sockets` uses the `websockets` asyncio server. Install it with
`python -m pip install 'orbit-sockets[websockets]'`:

```python
from orbit_sockets import WebSocketServer, WebSocketServerSettings


async def echo(session):
    while True:
        await session.send(await session.receive())


async def main():
    server = WebSocketServer(echo, WebSocketServerSettings(origins=("https://app.example",)))
    await server.start()
    try:
        await server.serve_forever()
    finally:
        await server.close()
```

The separately installable `orbit-sockets-go` implementation uses Go `coder/websocket`;
`orbit-sockets-rust` uses Tokio with `tokio-tungstenite`. These are standalone services deployed
behind ingress, not Core process plugins. Core's optional gRPC host supervises trusted local plugin
processes and is not a general microservice transport.

## Documentation

The package guides cover [architecture](docs/architecture/overview.md),
[operations and security](docs/operations/README.md), and [development](docs/development/README.md),
with [security guidance](docs/security/overview.md). The [documentation index](docs/README.md) links
to package policies.

## Development

```sh
python -m pip install -e '.[dev]'
pytest
ruff check .
ruff format --check .
mypy
python -m build
```

This contract package is in alpha and is not a production certification. Hosted CI, release
provenance, cross-implementation conformance, and deployment/load validation remain release gates.

Licensed under Apache-2.0.
