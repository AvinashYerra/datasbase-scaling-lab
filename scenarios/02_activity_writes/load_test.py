import asyncio
import asyncpg
import random
import statistics
import time


DB_CONFIG = {
    "user": "flashsale",
    "password": "password",
    "database": "flashsale",
    "host": "localhost",
    "port": 5432,
}

TOTAL_REQUESTS = 100_000
CONCURRENCY = 500
DB_POOL_SIZE = 90


async def execute_request(
    pool,
    pool_wait_times,
    db_exec_times,
    total_latencies,
):

    user_id = random.randint(1, 1_000_000)
    product_id = random.randint(1, 1_000_000)

    event_types = [
        "PAGE_VIEW",
        "PRODUCT_VIEW",
        "SEARCH",
        "ADD_TO_CART",
    ]

    event_type = random.choice(event_types)

    total_start = time.perf_counter()
    pool_wait_start = time.perf_counter()

    async with pool.acquire() as connection:

        pool_wait_time = (
            time.perf_counter() - pool_wait_start
        ) * 1000

        db_start = time.perf_counter()

        await connection.execute(
            """
            INSERT INTO user_activity (
                user_id,
                product_id,
                event_type
            )
            VALUES ($1, $2, $3)
            """,
            user_id,
            product_id,
            event_type,
        )

        db_exec_time = (
            time.perf_counter() - db_start
        ) * 1000

    # --------------------------------
    # Total request latency
    # --------------------------------
    total_latency = (
        time.perf_counter() - total_start
    ) * 1000

    pool_wait_times.append(pool_wait_time)
    db_exec_times.append(db_exec_time)
    total_latencies.append(total_latency)


async def worker(
    pool,
    request_count,
    pool_wait_times,
    db_exec_times,
    total_latencies,
):

    for _ in range(request_count):

        await execute_request(
            pool,
            pool_wait_times,
            db_exec_times,
            total_latencies,
        )


def percentile(values, percentile_value):

    index = int(len(values) * percentile_value)

    if index >= len(values):
        index = len(values) - 1

    return values[index]


def print_latency_stats(name, values):

    values.sort()

    print(f"\n{name}")

    print(
        f"Average : "
        f"{statistics.mean(values):.3f} ms"
    )

    print(
        f"P50     : "
        f"{percentile(values, 0.50):.3f} ms"
    )

    print(
        f"P95     : "
        f"{percentile(values, 0.95):.3f} ms"
    )

    print(
        f"P99     : "
        f"{percentile(values, 0.99):.3f} ms"
    )


async def main():

    print("Starting activity write load test...")

    print(f"Total requests : {TOTAL_REQUESTS}")
    print(f"Concurrency    : {CONCURRENCY}")
    print(f"DB pool size   : {DB_POOL_SIZE}")

    pool = await asyncpg.create_pool(
        **DB_CONFIG,
        min_size=DB_POOL_SIZE,
        max_size=DB_POOL_SIZE,
    )

    pool_wait_times = []
    db_exec_times = []
    total_latencies = []

    base_requests = (
        TOTAL_REQUESTS // CONCURRENCY
    )

    remainder = (
        TOTAL_REQUESTS % CONCURRENCY
    )

    workers = []

    start = time.perf_counter()

    for i in range(CONCURRENCY):

        request_count = (
            base_requests
            + (1 if i < remainder else 0)
        )

        workers.append(
            asyncio.create_task(
                worker(
                    pool,
                    request_count,
                    pool_wait_times,
                    db_exec_times,
                    total_latencies,
                )
            )
        )

    await asyncio.gather(*workers)

    elapsed = time.perf_counter() - start

    throughput = TOTAL_REQUESTS / elapsed

    print()
    print("========== RESULTS ==========")

    print(f"Total requests : {TOTAL_REQUESTS}")
    print(f"Concurrency    : {CONCURRENCY}")
    print(f"DB pool size   : {DB_POOL_SIZE}")

    print(
        f"Time           : "
        f"{elapsed:.3f} seconds"
    )

    print(
        f"Throughput     : "
        f"{throughput:.2f} writes/sec"
    )

    print_latency_stats(
        "POOL WAIT LATENCY",
        pool_wait_times,
    )

    print_latency_stats(
        "DB EXECUTION LATENCY",
        db_exec_times,
    )

    print_latency_stats(
        "TOTAL REQUEST LATENCY",
        total_latencies,
    )

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())