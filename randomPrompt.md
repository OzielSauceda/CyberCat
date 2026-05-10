Problem

The job failed because Redis lost connectivity during the chaos test, and the backend's EventBus consumer crashed when trying to reconnect. The key error in the logs is:
Code

EventBus consumer crashed: Error 111 connecting to redis:6379. Connection refused. — reconnecting in 2s
EventBus reconnect failed: Error -3 connecting to redis:6379. Temporary failure in name resolution. — will retry

This indicates that when Redis was killed mid-run (as intended by the test), the backend's EventBus consumer failed to handle the graceful degradation properly. The connection refused error (Error 111) followed by a DNS resolution failure (Error -3) suggests the backend isn't properly implementing the resilience pattern described in the workflow comments.
Root Cause

The test expects the backend to degrade gracefully when Redis is unavailable, but instead the EventBus consumer is crashing. According to the workflow's §A1 acceptance criteria:

    The simulator's --verify post-condition must pass
    No Python tracebacks should appear (indicating unhandled exceptions)
    The backend should stay responsive using safe_redis with bounded socket timeouts

The EventBus consumer crash violates the requirement that the backend degrades gracefully.
Solution

The EventBus consumer needs to catch Redis connection errors and implement retry logic with exponential backoff rather than crashing. Update the EventBus implementation to:

    Wrap Redis connections in try-except blocks to catch ConnectionError, TimeoutError, and DNS resolution failures
    Implement exponential backoff for reconnection attempts (starting at 2s as shown in logs, but with proper exception handling)
    Log warnings instead of crashing when Redis is temporarily unavailable
    Ensure the backend HTTP server remains responsive even when the EventBus consumer is disconnected from Redis

The workflow comment at line 14-17 specifically mentions that safe_redis + bounded socket timeouts should prevent hanging on getaddrinfo. Verify that:

    safe_redis wrapper is properly applied to all Redis operations
    Socket timeouts are configured (typical: 5-10 seconds)
    The EventBus consumer doesn't block the main request handling thread

Check the backend's Redis initialization and EventBus consumer code to ensure exceptions are caught at the consumer loop level, not allowed to propagate and crash the service.