# Stories

## Project Falcon checkout latency

- **Situation:** Checkout for Contoso Bank missed its p99 latency target at peak traffic.
- **Task:** Jordan led the fix for the Project Falcon checkout path.
- **Action:** Built a Redis-backed idempotency cache in Go and added cache eviction metrics.
- **Result:** p99 checkout latency fell 40%.
