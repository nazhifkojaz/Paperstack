"""Rate limiting middleware for Paperstack backend."""
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def get_identifier(request: Request) -> str:
    """Get client identifier for rate limiting.

    Uses IP address. Could be extended to use user ID for authenticated routes.
    """
    return get_remote_address(request)


# Create limiter instance
limiter = Limiter(key_func=get_identifier)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom handler for rate limit exceeded errors.

    Returns a 429 response with JSON body including retry_after seconds.
    Uses request.state.view_rate_limit set by slowapi.
    """
    import time

    # Get the rate limit info from request.state set by slowapi
    view_rate_limit = getattr(request.state, "view_rate_limit", None)

    # Default values if not available
    limit = 10
    remaining = 0
    reset_in = 60

    if view_rate_limit:
        # view_rate_limit is a tuple of (RateLimitItem, [key, ...])
        limit_item = view_rate_limit[0]
        limit = limit_item.amount

        # Get window stats for remaining count and reset time
        try:
            window_stats = request.app.state.limiter.limiter.get_window_stats(
                limit_item, *view_rate_limit[1]
            )
            reset_in = 1 + window_stats[0]
            remaining = window_stats[1]  # noqa: F841
        except Exception:
            pass

    retry_after = max(1, int(reset_in - time.time()))

    return JSONResponse(
        status_code=429,
        content={
            "detail": f"Rate limit exceeded. Try again in {retry_after} seconds.",
            "retry_after": retry_after
        },
        headers={
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(reset_in)),
            "Retry-After": str(retry_after)
        }
    )
