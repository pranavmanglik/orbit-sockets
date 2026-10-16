# Operations

Use a TLS-terminating ingress with explicit WebSocket upgrade support, request and connection
timeouts appropriate for long-lived sessions, and a bounded per-instance connection budget. Set
limits for message size, receive queues, write buffers, connection admission, and shutdown drain
time. Deployments must verify that proxies preserve upgrade headers and honor idle-timeout settings.
The Python server defaults to loopback binding, accepts clients without an `Origin` header, and
rejects browser clients until explicit HTTP(S) origins are configured. Its default message limit is
256 KiB. It bounds the configured origin and subprotocol lists to 64 entries each, rejects duplicate
entries, and requires subprotocols to use HTTP token syntax. The default missing-Origin allowance is
for native clients; it is not an identity check. Bind to a private interface or use explicit ingress
and firewall policy before exposing the service.

Authorize every connection and resource subscription. Validate browser origins against an explicit
allowlist; origin checks are not authentication. Do not put bearer credentials in URLs. Avoid
unbounded per-client fanout, retained session state, and unbounded broadcast queues. Drain sessions
on shutdown and let clients reconnect with application-defined backoff. The Python server waits for
handlers up to its configured shutdown timeout, then cancels remaining handler tasks.

The package provides a Python listener, but no deployment control plane, TLS termination, health
endpoint, metrics exporter, or cross-instance session coordination. Validate those controls in the
host application and deployment.
