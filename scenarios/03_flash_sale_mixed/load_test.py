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
CONCURRENCY = 1000
DB_POOL_SIZE = 90


# Flash-sale workload distribution
PRODUCT_READ_PERCENT = 60
INVENTORY_READ_PERCENT = 25
ACTIVITY_WRITE_PERCENT = 15


async def product_read(connection):
    product_id = random.randint(1, 1_000_000)

    await connection.fetchrow(
        """
        SELECT
            product_id,
            product_name,
            category,
            price,
            inventory
        FROM products
        WHERE product_id = $1
        """,
        product_id,
    )


async def inventory_read(connection):
    product_id = random.randint(1, 1_000_000)

    await connection.fetchval(
        """
        SELECT inventory
        FROM products
        WHERE product_id = $1
        """,
        product_id,
    )


async def activity_write(connection):
    user_id = random.randint(1, 1_000_000)
    product_id = random.randint(1, 1_000_000)

    event_type = random.choice(
        [
            "PAGE_VIEW",
            "PRODUCT_VIEW",
            "SEARCH",
            "ADD_TO_CART",
        ]
    )

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


async def execute_request(
    pool,
    metrics,
):

    operation = random.choices(
        [
            "product_read",
            "inventory_read",
            "activity_write",
        ],
        weights=[
            PRODUCT_READ_PERCENT,
            INVENTORY_READ_PERCENT,
            ACTIVITY_WRITE_PERCENT,
        ],
        k=1,
    )[0]

    total_start = time.perf_counter()

    pool_wait_start = time.perf_counter()

    async with pool.acquire() as connection:

        pool_wait_time = (
            time.perf_counter() - pool_wait_start
        ) * 1000

        db_start = time.perf_counter()

        if operation == "product_read":
            await product_read(connection)

        elif operation == "inventory_read":
            await inventory_read(connection)

        else:
            await activity_write(connection)

        db_exec_time = (
            time.perf_counter() - db_start
        ) * 1000

    total_latency = (
        time.perf_counter() - total_start
    ) * 1000

    metrics[operation]["pool_wait"].append(
        pool_wait_time
    )

    metrics[operation]["db_exec"].append(
        db_exec_time
    )

    metrics[operation]["total"].append(
        total_latency
    )


async def worker(
    pool,
    request_count,
    metrics,
):

    for _ in range(request_count):

        await execute_request(
            pool,
            metrics,
        )


def percentile(values, percentage):

    values = sorted(values)

    index = int(len(values) * percentage)

    if index >= len(values):
        index = len(values) - 1

    return values[index]


def print_metrics(operation, data):

    print()
    print(f"----- {operation.upper()} -----")

    print(
        f"Requests : "
        f"{len(data['total'])}"
    )

    print(
        f"Pool wait avg : "
        f"{statistics.mean(data['pool_wait']):.3f} ms"
    )

    print(
        f"DB exec avg   : "
        f"{statistics.mean(data['db_exec']):.3f} ms"
    )

    print(
        f"Total avg     : "
        f"{statistics.mean(data['total']):.3f} ms"
    )

    print(
        f"Total P50     : "
        f"{percentile(data['total'], 0.50):.3f} ms"
    )

    print(
        f"Total P95     : "
        f"{percentile(data['total'], 0.95):.3f} ms"
    )

    print(
        f"Total P99     : "
        f"{percentile(data['total'], 0.99):.3f} ms"
    )


async def main():

    print("Starting flash-sale mixed workload...")

    print(f"Total requests : {TOTAL_REQUESTS}")
    print(f"Concurrency    : {CONCURRENCY}")
    print(f"DB pool size   : {DB_POOL_SIZE}")

    print()
    print("Workload distribution:")
    print(
        f"Product reads     : "
        f"{PRODUCT_READ_PERCENT}%"
    )
    print(
        f"Inventory reads   : "
        f"{INVENTORY_READ_PERCENT}%"
    )
    print(
        f"Activity writes   : "
        f"{ACTIVITY_WRITE_PERCENT}%"
    )

    pool = await asyncpg.create_pool(
        **DB_CONFIG,
        min_size=DB_POOL_SIZE,
        max_size=DB_POOL_SIZE,
    )

    metrics = {
        "product_read": {
            "pool_wait": [],
            "db_exec": [],
            "total": [],
        },
        "inventory_read": {
            "pool_wait": [],
            "db_exec": [],
            "total": [],
        },
        "activity_write": {
            "pool_wait": [],
            "db_exec": [],
            "total": [],
        },
    }

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
                    metrics,
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
        f"{throughput:.2f} requests/sec"
    )

    print_metrics(
        "product_read",
        metrics["product_read"],
    )

    print_metrics(
        "inventory_read",
        metrics["inventory_read"],
    )

    print_metrics(
        "activity_write",
        metrics["activity_write"],
    )

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())