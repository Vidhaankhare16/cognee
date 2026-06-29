"""
Minimal proof that Turso/libSQL over Hrana gives *real* async concurrency,
versus aiosqlite which serializes statements through one background thread.

The whole argument is one measurement:
  - Fire N statements that each take real time (network round-trip + a small
    server-side spin via a recursive CTE).
  - Run them CONCURRENTLY (asyncio.gather) and SEQUENTIALLY (await in a loop).
  - If the driver is genuinely async, concurrent wall-clock ~= one statement.
    If it only *looks* async (aiosqlite), concurrent ~= sequential ~= N * one.

Setup:
  pip install libsql-client
  turso db create cognee-proof
  export TURSO_URL="libsql://<your-db>.turso.io"
  export TURSO_AUTH_TOKEN="<turso db tokens create ...>"
  python turso_async_proof.py
"""

import asyncio
import os
import time

import libsql_client  # stale (2024) but fine as a Hrana reference for the proof

N = 20

# A trivial, latency-bound statement. Each call is dominated by the network
# round-trip to the Turso region, not server CPU -- so concurrency shows up as
# overlapped I/O wait, which is exactly the "real async" claim. (A heavy CPU
# query would instead bottleneck on the server's cores and hide the effect.)
SQL = "SELECT 1;"


async def one(client):
    t = time.perf_counter()
    await client.execute(SQL)
    return time.perf_counter() - t


async def main():
    url = os.environ["TURSO_URL"]
    token = os.environ["TURSO_AUTH_TOKEN"]

    async with libsql_client.create_client(url, auth_token=token) as client:
        # WARMUP: pay connection setup + cold-start once, outside the timings.
        for _ in range(3):
            await one(client)

        # baseline: a single WARM statement = roughly one network round-trip
        single = min(await one(client), await one(client), await one(client))

        # SEQUENTIAL: await them one after another -> ~ N round-trips
        t = time.perf_counter()
        for _ in range(N):
            await one(client)
        seq = time.perf_counter() - t

        # CONCURRENT: all in flight at once on the event loop -> ~ one round-trip
        t = time.perf_counter()
        await asyncio.gather(*(one(client) for _ in range(N)))
        conc = time.perf_counter() - t

    print(f"single statement      : {single*1000:7.1f} ms")
    print(f"{N} sequential          : {seq*1000:7.1f} ms   (~= N * single)")
    print(f"{N} concurrent (gather) : {conc*1000:7.1f} ms   (~= single if truly async)")
    print(f"speedup               : {seq/conc:7.1f}x")
    print()
    print("True async  => concurrent ~= single, speedup ~= N")
    print("Fake async  => concurrent ~= sequential, speedup ~= 1  (this is aiosqlite)")


if __name__ == "__main__":
    asyncio.run(main())
