import asyncio
import asyncpg
import random
import time
import statistics


DB_CONFIG = {
    "user": "flashsale",
    "password": "password",
    "database": "flashsale",
    "host": "localhost",
    "port": 5432,
}

TOTAL_REQUESTS = 1_000_000
CONCURRENCY = 250
DB_POOL_SIZE = 90


async def execute_request(pool, latencies):
    product_id = random.randint(1, 1_000_000)

    start = time.perf_counter()

    try:
        async with pool.acquire() as connection:
            await connection.fetchrow(
                """
                SELECT *
                FROM products
                WHERE product_id = $1
                """,
                product_id,
            )

        latency = (time.perf_counter() - start) * 1000
        latencies.append(latency)

    except Exception:
        raise

async def worker(pool, request_count, latencies):
    for _ in range(request_count):
        await execute_request(pool, latencies)


async def main():
    latencies = []
    print("Starting load test...")
    print(f"Total requests : {TOTAL_REQUESTS}")
    print(f"Concurrency    : {CONCURRENCY}")
    print(f"DB pool size   : {DB_POOL_SIZE}")

    pool = await asyncpg.create_pool(
        **DB_CONFIG,
        min_size=DB_POOL_SIZE,
        max_size=DB_POOL_SIZE,
    )

    base_requests = TOTAL_REQUESTS // CONCURRENCY
    remainder = TOTAL_REQUESTS % CONCURRENCY

    start = time.perf_counter()

    workers = []

    for i in range(CONCURRENCY):
        request_count = base_requests + (1 if i < remainder else 0)

        workers.append(
            asyncio.create_task(
                worker(pool, request_count, latencies)
            )
        )

    await asyncio.gather(*workers)

    elapsed = time.perf_counter() - start

    throughput = TOTAL_REQUESTS / elapsed
    latencies.sort()
    print()
    print("========== RESULTS ==========")
    print(f"Total requests : {TOTAL_REQUESTS}")
    print(f"Concurrency    : {CONCURRENCY}")
    print(f"DB pool size   : {DB_POOL_SIZE}")
    print(f"Time           : {elapsed:.3f} seconds")
    print(f"Throughput     : {throughput:.2f} requests/sec")
    latencies.sort()

    p50 = latencies[int(len(latencies) * 0.50)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]

    print(f"Average latency: {statistics.mean(latencies):.3f} ms")
    print(f"P50 latency    : {p50:.3f} ms")
    print(f"P95 latency    : {p95:.3f} ms")
    print(f"P99 latency    : {p99:.3f} ms")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())