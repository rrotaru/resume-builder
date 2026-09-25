# Stories

## Real-time fraud-detection platform checkout latency

- **Situation:** Checkout for a top-10 US bank missed its p99 latency target at peak traffic.
- **Task:** Jordan led the fix for the real-time fraud-detection platform checkout path.
- **Action:** Built a Redis-backed idempotency cache in Go and added cache eviction metrics.
- **Result:** p99 checkout latency fell 40%.
