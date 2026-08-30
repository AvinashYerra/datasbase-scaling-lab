# Scenario 2 — User Activity Writes

## Objective

Simulate an e-commerce flash sale where a large number of concurrent users generate activity events.

Instead of simply reading product data, each request writes a user activity event to PostgreSQL.

The scenario is designed to investigate:

* Write throughput
* Concurrent database writes
* Connection-pool contention
* Database execution latency
* Request latency
* P95/P99 tail latency
* The effect of connection-pool size

---

## Workload

Each simulated request generates a random activity event:

```text
User
  ↓
Activity event
  ↓
Acquire DB connection
  ↓
INSERT
  ↓
PostgreSQL
```

The activity types are:

```text
PAGE_VIEW
PRODUCT_VIEW
SEARCH
ADD_TO_CART
```

The corresponding database operation is:

```sql
INSERT INTO user_activity (
    user_id,
    product_id,
    event_type
)
VALUES ($1, $2, $3);
```

---

## Database Setup

PostgreSQL 17 is running inside Docker.

The activity table contains:

```text
activity_id
user_id
product_id
event_type
event_timestamp
```

The initial experiment intentionally uses no secondary indexes on the activity columns so that we can establish a basic write-performance baseline.

---

## Environment

* PostgreSQL 17
* Docker
* Python 3.14
* asyncpg
* macOS
* Local PostgreSQL instance
* PostgreSQL `max_connections = 100`

---

# Experiments

## Experiment 1 — 10K Baseline

Configuration:

```text
Requests       : 10,000
Concurrency    : 100
DB pool        : 90
```

Results:

```text
Time       : 0.566 seconds
Throughput : 17,679 writes/sec
Avg latency: 5.568 ms
P50        : 5.038 ms
P95        : 9.260 ms
P99        : 22.438 ms
```

This establishes the initial write-throughput baseline.

---

## Experiment 2 — 1M Writes

Configuration:

```text
Requests       : 1,000,000
Concurrency    : 100
DB pool        : 90
```

Results:

```text
Time       : 55.451 seconds
Throughput : 18,034 writes/sec
Avg latency: 5.534 ms
P50        : 5.212 ms
P95        : 8.375 ms
P99        : 10.699 ms
```

The workload increased by 100× while throughput remained close to the 10K benchmark.

The database contained 1,010,000 rows afterward because the initial 10K benchmark was retained.

---

# Experiment 3 — Increasing Concurrency

The workload was changed to 100K writes while keeping the connection pool at 90.

### 100 Concurrent Producers

```text
Throughput : ~18,034 writes/sec
```

### 250 Concurrent Producers

```text
Throughput : ~17,658 writes/sec
Avg latency: 13.805 ms
P95        : 36.991 ms
P99        : 58.763 ms
```

### 500 Concurrent Producers

```text
Throughput : ~20,330 writes/sec
Avg latency: 23.486 ms
P95        : 73.471 ms
P99        : 114.545 ms
```

## Observation

Increasing concurrency did not produce proportional throughput increases.

Instead, latency increased significantly.

This indicates that the system is approaching a saturation point where additional concurrency primarily increases contention and waiting rather than increasing useful database throughput.

---

# Experiment 4 — Connection Pool Size

The workload was fixed at:

```text
Requests    : 100,000
Concurrency: 500
```

Only the database connection-pool size was changed.

| Pool | Throughput | Avg Latency |     P50 |     P95 |      P99 |
| ---: | ---------: | ----------: | ------: | ------: | -------: |
|   10 |   10,627/s |     45.47ms | 45.75ms | 97.47ms | 175.50ms |
|   25 |   14,414/s |     33.31ms | 32.49ms | 98.28ms | 152.21ms |
|   50 |   17,959/s |     26.65ms | 24.83ms | 86.78ms | 133.90ms |
|   90 |   20,330/s |     23.49ms | 20.59ms | 73.47ms | 114.55ms |

## Observation

Increasing the connection pool substantially improved throughput when the pool was very small.

However, the improvement became progressively smaller as the pool approached 90 connections.

This indicates diminishing returns from simply increasing the number of database connections.

---

# Experiment 5 — Separating Pool Wait from DB Execution

The benchmark was instrumented to measure:

```text
Pool wait time
+
Database execution time
=
Total request latency
```

### Pool Size = 10

Configuration:

```text
Requests    : 100,000
Concurrency: 500
Pool        : 10
```

Results:

```text
POOL WAIT

Average : 44.072 ms
P50     : 44.226 ms
P95     : 102.012 ms
P99     : 167.715 ms
```

```text
DB EXECUTION

Average : 0.595 ms
P50     : 0.581 ms
P95     : 0.804 ms
P99     : 0.990 ms
```

```text
TOTAL REQUEST

Average : 45.039 ms
P50     : 45.173 ms
P95     : 103.053 ms
P99     : 168.778 ms
```

### Key Finding

With only 10 database connections, most request latency came from waiting for a connection.

The actual PostgreSQL execution time remained below 1 ms even at P99.

---

# Experiment 6 — Pool Size = 90

Same workload:

```text
Requests    : 100,000
Concurrency: 500
Pool        : 90
```

Results:

```text
POOL WAIT

Average : 21.107 ms
P50     : 18.285 ms
P95     : 77.223 ms
P99     : 120.729 ms
```

```text
DB EXECUTION

Average : 3.221 ms
P50     : 3.018 ms
P95     : 5.293 ms
P99     : 7.070 ms
```

```text
TOTAL REQUEST

Average : 26.130 ms
P50     : 22.528 ms
P95     : 82.506 ms
P99     : 125.858 ms
```

---

# Key Findings

## 1. Application concurrency is not database concurrency

Having 500 concurrent requests does not mean PostgreSQL processes 500 operations simultaneously.

With a pool of 10:

```text
500 requests
     ↓
10 database connections
     ↓
many requests waiting
```

The connection pool becomes a bottleneck.

---

## 2. A larger pool reduces connection waiting

Increasing the pool from 10 to 90 increased throughput:

```text
10 connections → 10,627 writes/sec
90 connections → 20,330 writes/sec
```

At the same time, average latency decreased:

```text
45.47ms → 23.49ms
```

---

## 3. More connections do not provide unlimited scalability

The pool-size experiment shows diminishing returns.

The throughput improvement from:

```text
10 → 25
```

was much larger than:

```text
50 → 90
```

This suggests that another bottleneck begins to appear as more concurrent database operations are allowed.

---

## 4. Database execution itself can be very fast

With pool size 10:

```text
Average DB execution: 0.595 ms
P99 DB execution:     0.990 ms
```

Yet total request P99 was:

```text
168.778 ms
```

The difference was primarily connection-pool waiting.

---

## 5. Increasing the pool shifts the bottleneck

With pool size 90:

```text
Pool wait ↓
DB execution ↑
```

This suggests that allowing significantly more concurrent operations reduces application-side waiting but increases contention inside the database/system.

Therefore:

> Increasing the connection pool is not equivalent to increasing database capacity.

---

# Current Architecture

```text
                  Flash Sale Traffic
                         │
                         ▼
                500 concurrent users
                         │
                         ▼
                Application layer
                         │
                         ▼
                 Connection Pool
                         │
              ┌──────────┴──────────┐
              │                     │
          Waiting requests      Active DB work
              │                     │
              └──────────┬──────────┘
                         ▼
                    PostgreSQL
                         │
                         ▼
                  INSERT activity
```

---

# Next Experiments

The next stage will investigate the database itself rather than only the client-side load generator.

Planned measurements:

* PostgreSQL CPU utilization
* Active connections
* Active queries
* WAL generation
* Database/table size
* Transaction rate
* Checkpoint behavior
* Disk I/O

The goal is to identify where the actual saturation point occurs and distinguish:

```text
Application bottleneck
        vs
Connection-pool bottleneck
        vs
Database CPU bottleneck
        vs
Disk/WAL bottleneck
```

Ultimately, the experiment will move toward a more realistic flash-sale architecture where high-volume user activity is decoupled from synchronous database writes.
