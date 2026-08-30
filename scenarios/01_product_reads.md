# Scenario 1 — Product Reads

## Objective

Measure how PostgreSQL behaves under a high volume of concurrent product-read requests.

The scenario represents users repeatedly viewing products during an e-commerce flash sale.

## Environment

* PostgreSQL 17
* Docker
* 1,000,000 product records
* Python 3.14
* asyncpg
* macOS
* Primary-key index on `product_id`

## Query

```sql
SELECT *
FROM products
WHERE product_id = $1;
```

The query uses the primary-key index.

## Single-request baseline

`EXPLAIN ANALYZE` showed:

* Index Scan using `products_pkey`
* Execution time: approximately 0.098 ms
* Shared buffers hit: 4

## Connection limit

PostgreSQL was configured with:

```text
max_connections = 100
```

Attempting to create 250 database connections resulted in:

```text
TooManyConnectionsError
```

This demonstrated that application-level concurrency does not need to map one-to-one to database connections.

## Connection Pool Experiment

With 250 concurrent request producers:

| DB Pool |   Throughput |      P50 |      P95 |      P99 |
| ------: | -----------: | -------: | -------: | -------: |
|      10 | 14,528 req/s | 16.38 ms | 42.22 ms | 62.49 ms |
|      25 | 19,002 req/s | 11.81 ms | 35.13 ms | 55.32 ms |
|      50 | 18,558 req/s | 10.37 ms | 36.92 ms | 57.49 ms |
|      75 | 20,442 req/s |  6.09 ms | 32.31 ms | 51.95 ms |
|      90 | 22,045 req/s |  6.25 ms | 28.47 ms | 45.14 ms |

## 1 Million Request Test

Configuration:

```text
Total requests: 1,000,000
Concurrent request producers: 250
DB pool size: 90
```

Result:

```text
Time       : 45.995 seconds
Throughput : 21,741 req/s
Average    : 11.383 ms
P50        : 6.431 ms
P95        : 31.712 ms
P99        : 48.394 ms
Errors     : 0
```

## Key Findings

1. Indexed reads are extremely fast for a single request.
2. Increasing concurrency initially improves throughput.
3. Throughput does not scale linearly with concurrency.
4. PostgreSQL's connection limit becomes a constraint before arbitrary concurrency can be achieved.
5. Connection pooling allows many concurrent requests to share a smaller number of database connections.
6. Increasing the pool size reduces connection wait time, but eventually produces diminishing returns.
7. Tail latency (P95/P99) is important when evaluating flash-sale workloads.
8. One million requests can be processed successfully without errors, but sustained throughput is ultimately limited by the local system architecture.

## Next

Scenario 2 introduces high-volume **user activity writes**.

Instead of:

```text
User → SELECT → PostgreSQL
```

we will simulate:

```text
User
  ↓
Activity event
  ↓
INSERT
  ↓
PostgreSQL
```

This will allow us to investigate write throughput, WAL, transaction overhead, and contention.
