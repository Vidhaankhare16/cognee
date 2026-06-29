# Turso true-async proof (for cognee #3570)

Does Turso/libSQL give *real* async concurrency, or does it only look async like
`aiosqlite` (which runs SQLite on one background thread and drains a queue)?

This is a tiny, reproducible benchmark that answers it. It does **not** compare
the two backends' absolute speeds — that would be meaningless (network vs local
disk). It compares **each driver against itself**: the same statements run
**sequentially** vs **concurrently** (`asyncio.gather`). The number that matters
is the speedup ratio. A genuinely async driver overlaps the work and speeds up;
a driver that secretly serializes does not.

The two workloads differ on purpose, each chosen to expose the thing being tested:
- **Turso** uses `SELECT 1` so each call is dominated by network round-trip —
  the wait that real async overlaps.
- **aiosqlite** uses a small compute query so each call has measurable duration —
  enough to reveal serialization (a `SELECT 1` on in-memory SQLite is too fast to
  time reliably).

## Run it

```bash
pip install libsql-client aiosqlite

# aiosqlite contrast (no account needed)
python aiosqlite_contrast.py

# Turso path — point at any Turso DB. NOTE: use the https:// URL, not libsql://,
# so it runs over the Hrana HTTP /v2/pipeline transport. (The archived client's
# WebSocket handshake is rejected by current Turso servers — see caveat below.)
export TURSO_URL="https://<your-db>.turso.io"
export TURSO_AUTH_TOKEN="<token>"
python turso_async_proof.py
```

## Results (real Turso DB, aws-ap-northeast-1; 20 statements)

| Driver | 20 sequential | 20 concurrent | Speedup |
|---|---|---|---|
| libSQL over Hrana/HTTP (real Turso) | 2985 ms | 645 ms | **4.6×** |
| aiosqlite | 1136 ms | 1117 ms | **1.0×** |

aiosqlite gets **zero** benefit from concurrency (1.0× — concurrent ≈ sequential,
because it serializes on one background thread). Turso's statements genuinely
overlap on the wire (4.6×). Same benchmark harness, only the async driver swapped.

## Caveat (and why it's a floor, not a ceiling)

The archived `libsql-client` (last release 2024) opens a WebSocket with an old
Hrana handshake that current Turso servers reject (HTTP 400), so this ran over
the **HTTP** transport with **no connection pooling**. That caps the speedup well
below the theoretical 20×. So **4.6× is a floor** — a purpose-built async
SQLAlchemy dialect over `httpx` keep-alive (the proposal in #3570) removes that
ceiling. It's also why the design treats `libsql-client` as a Hrana reference,
not a hard dependency.
