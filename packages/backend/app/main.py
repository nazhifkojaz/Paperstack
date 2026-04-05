from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.http_client import HTTPClientState
from app.middleware.security import SecurityHeadersMiddleware
from app.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from app.api.routes import auth, pdfs, collections, tags, annotations, citations, sharing, api_keys
from app.api.routes import settings as settings_routes
from app.api.routes import auto_highlight, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Initializes shared resources on startup and cleans up on shutdown.
    """
    # Startup: Initialize HTTP clients for connection pooling
    HTTPClientState.init_http_clients(app)
    yield
    # Shutdown: Close HTTP clients gracefully
    await HTTPClientState.close_http_clients(app)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# Set up rate limiter
app.state.limiter = limiter

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up security headers
app.add_middleware(SecurityHeadersMiddleware)

# Register rate limit exception handler
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.VERSION}

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth")
app.include_router(pdfs.router, prefix=f"{settings.API_V1_STR}/pdfs", tags=["pdfs"])
app.include_router(collections.router, prefix=f"{settings.API_V1_STR}/collections", tags=["collections"])
app.include_router(tags.router, prefix=f"{settings.API_V1_STR}/tags", tags=["tags"])
app.include_router(annotations.router, prefix=f"{settings.API_V1_STR}/annotations", tags=["annotations"])
app.include_router(citations.router, prefix=f"{settings.API_V1_STR}/pdfs", tags=["citations"])
app.include_router(citations.global_router, prefix=f"{settings.API_V1_STR}/citations", tags=["citations"])
app.include_router(sharing.router, prefix=f"{settings.API_V1_STR}", tags=["sharing"])
app.include_router(sharing.public_router, prefix=f"{settings.API_V1_STR}", tags=["sharing"])
app.include_router(settings_routes.router, prefix=f"{settings.API_V1_STR}/settings", tags=["settings"])
app.include_router(api_keys.router, prefix=f"{settings.API_V1_STR}/settings", tags=["settings"])
app.include_router(auto_highlight.router, prefix=f"{settings.API_V1_STR}/auto-highlight", tags=["auto-highlight"])
app.include_router(chat.router, prefix=f"{settings.API_V1_STR}/chat", tags=["chat"])

