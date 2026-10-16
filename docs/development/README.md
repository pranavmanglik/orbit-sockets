# Development

Install development dependencies with `python -m pip install -e '.[dev]'`. Run `pytest`,
`ruff check .`, `ruff format --check .`, `mypy`, and `python -m build` before a change is proposed.

Contract changes must update the bounded Python values, language-neutral schema when present,
implementation conformance suites, compatibility documentation, and release notes together. Tests
should cover size boundaries, Unicode validation, cancellation, transport flow control, close
handshake, overload, peer disconnect, and secret-safe failures using deterministic local transports.
## Local interpreter matrix

The Python suite passed **29 tests on each of CPython 3.11.14, 3.12.14, 3.13.15, and 3.14.7**.
Ruff lint and formatting, strict mypy, and isolated wheel/source builds passed for each interpreter.
These checks use local deterministic transports; they do not establish ingress, proxy, load, or
multi-instance behavior.
