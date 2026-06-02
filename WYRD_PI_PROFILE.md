# WYRD Pi Hardware Profile

**Date:** 2026-05-14  
**Device:** Raspberry Pi 5 Model B Rev 1.1 (aarch64)  
**RAM:** 16GB (13,824 MB available)  
**Disk:** 305.3 GB free of 468.9 GB  

## Benchmark Results

### ECS Core

| Metric | Value | Notes |
|--------|-------|-------|
| Import time | 0.243s | Cold start, includes Pydantic |
| Import RSS | 22.5 MB | One-time cost |
| 100 entity+component creation | 0.001s (0.01ms/entity) | Negligible |
| 1000 entity queries | 0.004s (0.004ms/query) | Sub-millisecond |
| 100 entity RSS delta | 232 KB (0.23 MB) | ~2.3 KB/entity |

### Yggdrasil Spatial

| Metric | Value |
|--------|-------|
| 150 nodes (3 zones × 5 regions × 10 locations) | 0.005s (0.03ms/node) |
| 1000 location lookups | <0.001s (0.000ms/lookup) |

### SQLite WAL

| Metric | Value |
|--------|-------|
| 1000 inserts | 0.045s (0.04ms/insert) |
| 100 indexed queries | 0.020s (0.20ms/query) |
| WAL mode | ✅ Active |
| busy_timeout | 5000ms ✅ |

### Concurrent Coexistence (Mímir + WYRD)

| Metric | Value |
|--------|-------|
| 100 concurrent dual-DB reads | 0.002s (0.02ms/read) |
| Mímir journal_mode | ✅ wal |
| WYRD journal_mode | ✅ wal |
| Conflict detection | None — both DBs coexist cleanly |

### Nerve Bridge Latency

| Metric | Value |
|--------|-------|
| Avg latency (50 events) | 0.02ms |
| Min latency | 0.01ms |
| Max latency | 0.14ms |

## Verdict

**✅ WYRD is fully Pi-viable.** All metrics well within acceptable thresholds:

- **Memory:** 22.5 MB import footprint + ~2.3 KB/entity — sustainable at scale
- **CPU:** Sub-millisecond entity creation and queries
- **SQLite:** WAL mode active on both DBs, no coexistence conflicts, zero-contention concurrent reads
- **Nerve bridge:** 0.02ms average latency — effectively instantaneous
- **Disk:** 305 GB free — ample room for world state growth

## Configuration Applied

- `PRAGMA journal_mode=WAL` confirmed on both `runa_memory.db` and `wyrd_hermes.db`
- `PRAGMA busy_timeout=5000` set for 5-second conflict resolution
- No conflicts detected during concurrent read testing