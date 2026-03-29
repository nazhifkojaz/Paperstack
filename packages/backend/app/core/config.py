from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Paperstack"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/v1"

    # Database
    DATABASE_URL: str
    DEV_DATABASE_URL: str | None = None

    @property
    def effective_database_url(self) -> str:
        return self.DEV_DATABASE_URL or self.DATABASE_URL
    
    # Security
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_EXPIRE_DAYS: int = 30
    ENCRYPTION_KEY: str
    
    # GitHub OAuth
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str

    # Google OAuth + Drive
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    BACKEND_URL: str = "http://localhost:8000"  # Used to construct OAuth redirect URIs

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_OAUTH: str = "10/minute"
    RATE_LIMIT_AUTH_REFRESH: str = "20/minute"
    RATE_LIMIT_AUTH_ME: str = "60/minute"
    RATE_LIMIT_AUTH_LOGOUT: str = "30/minute"

    # LLM Providers (in-house keys)
    GLM_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    # Auto-highlight rate limits
    RATE_LIMIT_AUTO_HIGHLIGHT_ANALYZE: str = "3/minute"
    RATE_LIMIT_AUTO_HIGHLIGHT_QUOTA: str = "30/minute"
    RATE_LIMIT_AUTO_HIGHLIGHT_CACHE: str = "30/minute"
    RATE_LIMIT_API_KEYS: str = "10/minute"

    # Embedding (backend-held key, separate from user chat keys)
    GEMINI_EMBEDDING_KEY: str | None = None

    # Chat rate limits
    RATE_LIMIT_CHAT_MESSAGE: str = "20/minute"
    RATE_LIMIT_CHAT_CONVERSATIONS: str = "30/minute"
    RATE_LIMIT_SEMANTIC_SEARCH: str = "10/minute"
    RATE_LIMIT_CHAT_EXPLAIN: str = "10/minute"

    # HTTP Client Connection Pooling
    HTTP_CONNECTION_LIMIT: int = 100  # Max concurrent connections
    HTTP_TIMEOUT_CONNECT: float = 10.0  # Connection timeout in seconds
    HTTP_TIMEOUT_READ: float = 120.0  # Read timeout in seconds (for LLM streaming)
    HTTP_MAX_KEEPALIVE: int = 20  # Max idle connections to keep alive

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()
