# Gunicorn Configuration
# See: https://docs.gunicorn.org/en/stable/settings.html

# Request timeout in seconds
timeout = 120

# preload_app: DO NOT ENABLE THIS
# Setting preload_app = True causes fork-safety issues with database connections:
#
# Issue: DatabaseSessionService initializes psycopg2 connections in the master process.
# When Gunicorn forks workers, these connections are inherited by child processes.
#
# Symptoms:
#   - macOS: Immediate SIGKILL crash (Objective-C runtime detects unsafe fork)
#   - Linux: Silent failures (random DB errors, SSL issues, connection pool exhaustion)
#
# Solution: Keep preload_app = False (default)
# This ensures each worker initializes its own clean database connections post-fork.
#
# Trade-off: ~150MB extra memory per worker (acceptable for stability)
# See: plans/fix-gunicorn-async-crash.md for full analysis
preload_app = False

# Number of worker processes
workers = 2

# Number of threads per worker
threads = 2