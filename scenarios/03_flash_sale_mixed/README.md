# Scenario 3 — Flash Sale Mixed Workload

## Objective

Simulate a realistic e-commerce flash-sale workload where many users simultaneously perform a mixture of product reads, inventory reads, and user activity writes.

The goal is to understand how increasing concurrency affects:

* Overall throughput
* Request latency
* Connection pool wait time
* Database execution time
* Read latency under concurrent writes
* System behavior near connection-pool saturation

---

## Workload

Each request randomly performs one of three operations:

| Operation      | Percentage | Description                           |
| -------------- | ---------: | ------------------------------------- |
| Product read   |        60% | Fetch product details by `product_id` |
| Inventory read |        25% | Fetch current inventory               |
| Activity write |        15% | Record a user activity event          |

The workload therefore represents a read-heavy e-commerce application with a continuous stream of writes.

```text
                     500–1000 concurrent users
                              |
                              v
                    +-------------------+
                    | Request generator |
                    +---------+---------+
                              |
              +---------------+---------------+
              |               |               |
             60%             25%             15%
              |               |               |
              v               v               v
        Product READ    Inventory READ   Activity WRITE
              |               |               |
              +---------------+---------------+
                              |
                              v
                         PostgreSQL
```

---

## Environment

* Database: PostgreSQL 17
* PostgreSQL: Docker container
* Database: `flashsale`
* Product records: 1,000,000
* DB `max_connections`: 100
* Application DB pool: 90
* Load generator: Python + `asyncpg`

The database connection limit is intentionally kept at the PostgreSQL default used in this experiment. We do not increase the pool beyond the available database connections.

---

# Experiment 1 — 500 Concurrent Users

### Configuration

```text
Total requests : 100,000
Concurrency    : 500
DB pool size   : 90
```

### Results

| Metric            | Product Read | Inventory Read | Activity Write |
| ----------------- | -----------: | -------------: | -------------: |
| Requests          |       60,089 |         24,834 |         15,077 |
| Avg total latency |    20.575 ms |      20.732 ms |      23.958 ms |
| P95               |    66.939 ms |      66.319 ms |      72.770 ms |
| P99               |   105.959 ms |     103.747 ms |     110.549 ms |
| Avg pool wait     |    16.909 ms |      17.048 ms |      17.230 ms |
| Avg DB execution  |     1.604 ms |       1.618 ms |       4.651 ms |

### Overall

```text
Time       : 4.404 seconds
Throughput : 22,707 requests/sec
```

---

# Experiment 2 — 1,000 Concurrent Users

The workload was kept identical while doubling concurrency.

### Configuration

```text
Total requests : 100,000
Concurrency    : 1,000
DB pool size   : 90
```

### Results

| Metric            | Product Read | Inventory Read | Activity Write |
| ----------------- | -----------: | -------------: | -------------: |
| Requests          |       60,201 |         24,904 |         14,895 |
| Avg total latency |    42.785 ms |      42.810 ms |      46.279 ms |
| P95               |   146.846 ms |     145.900 ms |     150.690 ms |
| P99               |   235.214 ms |     233.991 ms |     237.321 ms |
| Avg pool wait     |    38.944 ms |      38.967 ms |      39.160 ms |
| Avg DB execution  |     1.694 ms |       1.699 ms |       4.964 ms |

### Overall

```text
Time       : 4.620 seconds
Throughput : 21,643 requests/sec
```

---

# Comparison

| Metric                 | 500 Concurrency | 1,000 Concurrency |
| ---------------------- | --------------: | ----------------: |
| Throughput             |    22,707 req/s |      21,643 req/s |
| Product P99            |          106 ms |            235 ms |
| Inventory P99          |          104 ms |            234 ms |
| Activity P99           |          111 ms |            237 ms |
| Product pool wait      |         16.9 ms |           38.9 ms |
| Inventory pool wait    |         17.0 ms |           39.0 ms |
| Write pool wait        |         17.2 ms |           39.2 ms |
| Product DB execution   |         1.60 ms |           1.69 ms |
| Inventory DB execution |         1.62 ms |           1.70 ms |
| Write DB execution     |         4.65 ms |           4.96 ms |

---

# Key Findings

## 1. Doubling concurrency did not increase throughput

Increasing concurrency from 500 to 1,000 resulted in:

```text
22,707 req/s
      ↓
21,643 req/s
```

Throughput decreased by approximately 4.7%.

This indicates that the system was approaching saturation.

More concurrent users did not translate into more completed work.

---

## 2. Connection pool wait became the dominant latency component

At 500 concurrent users:

```text
Pool wait       ≈ 17 ms
DB execution    ≈ 1.6–4.7 ms
```

At 1,000 concurrent users:

```text
Pool wait       ≈ 39 ms
DB execution    ≈ 1.7–5.0 ms
```

The increase in total latency was therefore primarily driven by connection acquisition wait rather than SQL execution.

---

## 3. Database execution time remained relatively stable

Product reads:

```text
1.604 ms → 1.694 ms
```

Inventory reads:

```text
1.618 ms → 1.699 ms
```

Activity writes:

```text
4.651 ms → 4.964 ms
```

The SQL operations themselves did not experience a comparable increase to the overall request latency.

---

## 4. Tail latency became significantly worse

Product-read P99:

```text
105.959 ms → 235.214 ms
```

Inventory-read P99:

```text
103.747 ms → 233.991 ms
```

Activity-write P99:

```text
110.549 ms → 237.321 ms
```

This is important for a flash-sale application because users experience the **end-to-end request latency**, not just database execution time.

---

# Conclusion

The experiment demonstrates a common scaling problem:

```text
More concurrent users
        |
        v
More requests competing for
a fixed number of DB connections
        |
        v
Connection pool wait increases
        |
        v
Request latency increases
        |
        v
Throughput stops scaling
```

The database was not simply becoming slower at executing queries. The major bottleneck observed in this experiment was **connection contention**.

Increasing the number of application requests beyond the available database connection capacity therefore resulted primarily in increased waiting and tail latency rather than increased throughput.

---

# What This Means for a Real Flash Sale

A production e-commerce system should not necessarily solve this problem by continuously increasing the database connection pool.

A database has finite resources, and allowing every application server to create large numbers of connections can make the database itself unstable.

Common approaches include:

* Connection pooling
* Limiting application concurrency
* Caching frequently accessed product data
* Read replicas for read-heavy workloads
* Asynchronous processing for non-critical writes
* Message queues for high-volume activity events
* Batching database writes
* Separating transactional workloads from analytics/event workloads

The next scenarios will explore some of these techniques.

---

## Next Scenario

**Scenario 4 — Flash Sale Inventory Contention**

We will simulate many users attempting to purchase the same limited-inventory product simultaneously.

The focus will shift from performance to **correctness under concurrency**:

```text
100 units available
        |
        v
1000 users attempt purchase
        |
        v
Concurrent inventory updates
        |
        +----> Lost updates?
        |
        +----> Overselling?
        |
        +----> Row locking?
        |
        +----> Transaction isolation?
        |
        +----> Atomic decrement?
```

This will introduce PostgreSQL transactions, row-level locking, and concurrency-control techniques.
