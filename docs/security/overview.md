# Security

WebSocket sessions are long-lived, resource-consuming connections. The Python server applies
connection, message, receive-queue, write-buffer, and timeout bounds, but these limits are per
process and must be multiplied by the deployment replica count. Applications still need explicit
origin policy, authentication, per-message authorization, and graceful shutdown. Origin validation
does not replace authentication or CSRF defenses. Enforce TLS at a trusted ingress and correctly
configure forwarded client identity.

The default Python configuration allows a missing `Origin` header and rejects browser origins
until explicit origins are configured. A non-browser client can omit or forge this header, so
origin checks must never be treated as identity verification. For browser-only endpoints, explicitly
configure the allowlist and authenticate every connection and protected subscription. The server
does not provide authentication, authorization, rate limiting, or TLS termination.

Do not log message bodies, authorization headers, URL query strings containing secrets, session
tokens, or raw provider exceptions. Keep authentication and authorization in `orbit-auth`; this
package defines transport-level values only.
