from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

# Notes on connection lifecycle (Neon free tier + long background tasks):
#   * pool_pre_ping validates a connection at checkout time only. If a session
#     holds a connection across a long external await (LLM call), it can die
#     idle and the next query fails. The real fix is short-scoped sessions in
#     background tasks; this engine config is a best-effort mitigation.
#   * server_settings.tcp_keepalives_* makes Postgres send keepalives on its
#     side of the socket so Neon's load balancer is more likely to notice and
#     cleanly close dead connections (lets pool_pre_ping catch them sooner).
#   * pool_recycle ensures no pooled connection lives longer than N seconds,
#     so a stale connection is replaced before it gets used.
engine = create_async_engine(
    settings.effective_database_url,
    pool_pre_ping=True,
    pool_recycle=1800,  # 30 min
    connect_args={
        "server_settings": {
            "tcp_keepalives_idle": "30",
            "tcp_keepalives_interval": "10",
            "tcp_keepalives_count": "3",
            "statement_timeout": "60000",  # 60s — kill runaway queries
        },
    },
)

SessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
