import argparse
import asyncio
import asyncpg
import time


DB_CONFIG = {
    "user": "flashsale",
    "password": "password",
    "database": "flashsale",
    "host": "localhost",
    "port": 5432,
}

TOTAL_REQUESTS = 1000
CONCURRENCY = 500
DB_POOL_SIZE = 90

PRODUCT_ID = 1
INITIAL_INVENTORY = 100


async def purchase_naive(connection, results):
    inventory = await connection.fetchval(
        """
        SELECT inventory
        FROM flash_sale_inventory
        WHERE product_id = $1
        """,
        PRODUCT_ID,
    )

    if inventory <= 0:
        results["sold_out"] += 1
        return

    # Deliberately create a race-condition window.
    await asyncio.sleep(0.001)

    await connection.execute(
        """
        UPDATE flash_sale_inventory
        SET inventory = inventory - 1
        WHERE product_id = $1
        """,
        PRODUCT_ID,
    )

    results["successful"] += 1


async def purchase_for_update(connection, results):
    async with connection.transaction():

        inventory = await connection.fetchval(
            """
            SELECT inventory
            FROM flash_sale_inventory
            WHERE product_id = $1
            FOR UPDATE
            """,
            PRODUCT_ID,
        )

        if inventory <= 0:
            results["sold_out"] += 1
            return

        await asyncio.sleep(0.001)

        await connection.execute(
            """
            UPDATE flash_sale_inventory
            SET inventory = inventory - 1
            WHERE product_id = $1
            """,
            PRODUCT_ID,
        )

        results["successful"] += 1


async def purchase_atomic(connection, results):
    result = await connection.execute(
        """
        UPDATE flash_sale_inventory
        SET inventory = inventory - 1
        WHERE product_id = $1
          AND inventory > 0
        """,
        PRODUCT_ID,
    )

    if result == "UPDATE 1":
        results["successful"] += 1
    else:
        results["sold_out"] += 1


async def purchase(pool, strategy, results):

    async with pool.acquire() as connection:

        try:

            if strategy == "naive":
                await purchase_naive(connection, results)

            elif strategy == "lock":
                await purchase_for_update(connection, results)

            elif strategy == "atomic":
                await purchase_atomic(connection, results)

        except Exception as e:
            results["errors"] += 1
            results["error_messages"].append(str(e))


async def worker(pool, strategy, requests, results):

    for _ in range(requests):
        await purchase(
            pool,
            strategy,
            results,
        )


async def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--strategy",
        choices=["naive", "lock", "atomic"],
        required=True,
    )

    args = parser.parse_args()

    strategy = args.strategy

    print("Starting inventory contention test...")
    print(f"Strategy       : {strategy}")
    print(f"Total requests : {TOTAL_REQUESTS}")
    print(f"Concurrency    : {CONCURRENCY}")
    print(f"DB pool size   : {DB_POOL_SIZE}")
    print(f"Initial stock  : {INITIAL_INVENTORY}")

    pool = await asyncpg.create_pool(
        **DB_CONFIG,
        min_size=DB_POOL_SIZE,
        max_size=DB_POOL_SIZE,
    )

    results = {
        "successful": 0,
        "sold_out": 0,
        "errors": 0,
        "error_messages": [],
    }

    requests_per_worker = TOTAL_REQUESTS // CONCURRENCY

    start = time.perf_counter()

    workers = []

    for _ in range(CONCURRENCY):

        workers.append(
            asyncio.create_task(
                worker(
                    pool,
                    strategy,
                    requests_per_worker,
                    results,
                )
            )
        )

    await asyncio.gather(*workers)

    elapsed = time.perf_counter() - start

    final_inventory = await pool.fetchval(
        """
        SELECT inventory
        FROM flash_sale_inventory
        WHERE product_id = $1
        """,
        PRODUCT_ID,
    )

    await pool.close()

    throughput = TOTAL_REQUESTS / elapsed

    print()
    print("========== RESULTS ==========")

    print(f"Strategy       : {strategy}")
    print(f"Total requests : {TOTAL_REQUESTS}")
    print(f"Successful     : {results['successful']}")
    print(f"Sold out       : {results['sold_out']}")
    print(f"Errors         : {results['errors']}")
    print(f"Final inventory: {final_inventory}")

    print(f"Time           : {elapsed:.3f} seconds")
    print(f"Throughput     : {throughput:.2f} requests/sec")

    print()
    print("EXPECTED")
    print("----------------")
    print(f"Initial stock  : {INITIAL_INVENTORY}")

    if strategy == "naive":
        print("Race condition expected.")
    else:
        print("Overselling should NOT occur.")

    oversold_units = max(
    0,
    results["successful"] - INITIAL_INVENTORY
    )

    correct = (
        results["successful"] <= INITIAL_INVENTORY
        and final_inventory >= 0
    )

    print()
    print("CORRECTNESS")
    print("----------------")
    print(f"Oversold units : {oversold_units}")
    print(f"Inventory valid: {correct}")

if __name__ == "__main__":
    asyncio.run(main())