# Orbit Sockets architecture

`orbit-sockets` contains provider-neutral WebSocket message/session contracts and an optional
Python standalone listener backed by the `websockets` asyncio server. The Go and Rust listeners are
separately installable packages. Applications select and deploy one implementation; this package
does not add a framework or another ASGI server.

```text
application ──> orbit-sockets contracts + optional Python listener
             ├─> orbit-sockets-go (coder/websocket)
             └─> orbit-sockets-rust (Tokio/tokio-tungstenite)
```

These listeners are services deployed behind ingress, not local Core process plugins. Core's
gRPC process-plugin host is for trusted local extension lifecycle and typed capability calls; it
is not used to forward each browser WebSocket frame or to replace a general microservice transport.

## Shared contract

`SocketMessage` accepts text or binary data and bounds encoded message size to 1 MiB. `SocketClose`
validates protocol-reserved close codes and limits a UTF-8 close reason to 123 bytes. Repr output
shows message kind/size and close code/reason size without the message body or reason text.

`SocketSession` defines one bidirectional session. Implementations must bound receive buffering,
apply transport flow control when sending, propagate task cancellation, and make close idempotent.
A successful `send()` reports transport acceptance, not peer receipt or application-level
acknowledgement. Applications that need delivery confirmation must define their own protocol.

## Python listener

Install the optional listener dependency with `pip install 'orbit-sockets[websockets]'`. The Python
server binds to loopback on port 8765 by default, listens at `/ws`, permits a missing `Origin`
header by default, and caps messages at 256 KiB by default. Its `WebSocketServerSettings` bounds
connections, receive queue size, write buffer, handshake/ping/close timeouts, and shutdown drain.
The listener owns its sockets and accepted session lifecycle; the application supplies the handler
and remains responsible for authorization and shared state.

Origin matching is a browser cross-site defense, not authentication. The default missing-Origin
allowance supports native clients and does not prove client identity. For browser endpoints, set an
explicit exact HTTP(S) origin allowlist and independently authenticate and authorize connections
and subscriptions. The listener has no TLS configuration: terminate TLS at a trusted ingress or
provide a separately reviewed secure transport arrangement.

## Separate protocols and ownership

`orbit-realtime` owns Server-Sent Events. WebTransport remains a separate capability because
HTTP/3/QUIC has distinct stream, datagram, TLS, ingress, and lifecycle requirements. WebRTC has
different signaling and ICE/media lifecycle and lives in its own packages. None of these protocols
is silently implemented by the WebSocket session contract.

Applications own identity, per-message authorization, upstream resources, broadcast fanout,
replay, and cross-instance scaling. Provider and language-specific implementations own their
transport lifecycle and failure mapping and should demonstrate conformance to the shared contract.

## Stability

The APIs are alpha. Hosted conformance, ingress behavior, capacity/load behavior, and production
deployment remain separate release validation gates; the existence of a local listener is not
evidence that these gates passed.
