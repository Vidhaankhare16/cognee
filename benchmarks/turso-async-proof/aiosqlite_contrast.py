"""
Contrast: the SAME concurrent-vs-sequential test against aiosqlite.

aiosqlite is SQLAlchemy's "async" sqlite driver, but it runs SQLite on ONE
background thread and drains a queue -- so statements serialize no matter how
many tasks await them. A measurable per-statement cost (a recursive CTE spin)
makes that visible: concurrent ~= sequential, speedup ~= 1x.

This is the foil to the Turso run, where 20 concurrent network statements
overlapped for a 4.6x speedup. Same harness, opposite outcome.

    python aiosqlite_contrast.py
"""

import asyncio
import time

import aiosqlite

N = 20

# CPU-bound spin so each statement takes measurable time on aiosqlite's single
# worker thread. (aiosqlite has no network wait to overlap; the point is that
# even with real per-statement duration, concurrency buys nothing.)
SQL = """
WITH RECURSIVE c(x) AS (
    SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 400000
)
SELECT count(*) FROM c;
"""


async def one(db):
    t = time.perf_counter()
    await db.execute(SQL)
    return time.perf_counter() - t


async def main():
    async with aiosqlite.connect(":memory:") as db:
        for _ in range(2):  # warmup
            await one(db)

        single = min(await one(db), await one(db))

        t = time.perf_counter()
        for _ in range(N):
            await one(db)
        seq = time.perf_counter() - t

        t = time.perf_counter()
        await asyncio.gather(*(one(db) for _ in range(N)))
        conc = time.perf_counter() - t

    print(f"single statement      : {single*1000:7.1f} ms")
    print(f"{N} sequential          : {seq*1000:7.1f} ms")
    print(f"{N} concurrent (gather) : {conc*1000:7.1f} ms")
    print(f"speedup               : {seq/conc:7.1f}x   (aiosqlite: ~1x = serialized)")


if __name__ == "__main__":
    asyncio.run(main())
