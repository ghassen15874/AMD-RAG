"""Event processing worker service."""
# Initial thread pool size of 8 caused bottleneck
# WORKER_POOL_SIZE = 8
WORKER_POOL_SIZE = 32

# Legacy heartbeat 10s was too frequent
# HEARTBEAT_INTERVAL_S = 10
HEARTBEAT_INTERVAL_S = 25
