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
    RATE_LIMIT_AUTH_OAUTH: str = "10/minute"
    RATE_LIMIT_AUTH_REFRESH: str = "20/minute"
    RATE_LIMIT_AUTH_ME: str = "60/minute"
    RATE_LIMIT_AUTH_LOGOUT: str = "30/minute"

    # LLM Provider (in-house key)
    OPENROUTER_API_KEY: str | None = None

    # Auto-highlight rate limits
    RATE_LIMIT_AUTO_HIGHLIGHT_QUOTA: str = "30/minute"
    RATE_LIMIT_AUTO_HIGHLIGHT_CACHE: str = "30/minute"

    # Auto-highlight thorough-mode batch concurrency. 1 preserves the historic
    # sequential behavior. Raising it overlaps LLM network calls across batches
    # (bounded by _MAX_THOROUGH_CONCURRENCY in the route module).
    AUTO_HIGHLIGHT_THOROUGH_CONCURRENCY: int = 1
    RATE_LIMIT_API_KEYS: str = "10/minute"
    RATE_LIMIT_PDF_CHECK_URL: str = "10/minute"
    RATE_LIMIT_REINDEX: str = "5/minute"

    # Embedding — server key reused from OPENROUTER_API_KEY

    # OpenRouter free-tier daily request limit (for soft-gating at 90%).
    OPENROUTER_FREE_TIER_LIMIT: int = 1000
    GLOBAL_QUOTA_WARNING_PCT: int = 90

    # Daily free-tier quotas for users without their own LLM API key
    QUOTA_CHAT_DAILY: int = 50
    QUOTA_EXPLAIN_PARAPHRASE_DAILY: int = 30
    QUOTA_AUTO_HIGHLIGHT_QUICK_DAILY: int = 5
    QUOTA_AUTO_HIGHLIGHT_THOROUGH_DAILY: int = 3
    QUOTA_SUMMARY_DAILY: int = 10
    # Bulk collection summarization: papers processed concurrently (VPS is
    # 2 vCPU — mirror the auto-highlight thorough cap rationale).
    SUMMARY_BULK_CONCURRENCY: int = 2

    # Near-duplicate detection threshold (cosine similarity) for collections.
    DUPLICATE_SIMILARITY_THRESHOLD: float = 0.95

    # OpenRouter reasoning (thinking) mode
    OPENROUTER_REASONING_ENABLED: bool = True
    OPENROUTER_REASONING_EFFORT: str = "medium"  # "low" | "medium" | "high"
    OPENROUTER_REASONING_TIMEOUT_READ: float = (
        180.0  # Longer timeout for reasoning calls
    )

    # Chat rate limits
    RATE_LIMIT_CHAT_CONVERSATIONS: str = "30/minute"
    RATE_LIMIT_SEMANTIC_SEARCH: str = "10/minute"

    # Chunking (Phase C, Phase 3): the chunker sizes by TOKENS, not characters,
    # using tiktoken's cl100k_base encoding (matches the embedding model family
    # and uses the 8K context window properly). CHUNK_SIZE/CHUNK_OVERLAP are
    # retained for backwards compatibility but are no longer read by the chunker.
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150
    CHUNK_SIZE_TOKENS: int = 400
    CHUNK_OVERLAP_TOKENS: int = 64

    # Extraction backend: which DocumentExtractor implementation produces the
    # ExtractedDocument that the chunker walks. "pymupdf" is the legacy
    # font-heuristic extractor; "pymupdf4llm" is the new Markdown-based one
    # (Phase C). Default flipped to "pymupdf4llm" in Phase 6 after the golden
    # corpus passed; the legacy backend remains available via config override.
    EXTRACTION_BACKEND: str = "pymupdf4llm"  # "pymupdf" | "pymupdf4llm"

    # Contextual retrieval: prepend "Paper: <title>\nSection: <section>" to
    # each chunk's text before embedding. The raw `content` column is
    # unaffected; only the embedding vector uses the contextualized text.
    # Legacy chunks (pre-this-flag) and any chunk indexed while this is False
    # embed the raw content directly.
    CONTEXTUAL_RETRIEVAL_ENABLED: bool = True

    # Retrieval top_k values
    CHAT_TOP_K_SINGLE_PDF: int = 10
    CHAT_TOP_K_COLLECTION: int = 8
    EXPLAIN_TOP_K: int = 4

    # Hybrid search weights
    HYBRID_SEMANTIC_WEIGHT: float = 0.7
    HYBRID_KEYWORD_WEIGHT: float = 0.3

    # Optional cross-encoder reranker (second retrieval stage). None = disabled
    # (behaviour identical to the pre-reranker path). When set, retrieval pulls a
    # RERANKER_POOL_K candidate pool via hybrid search and re-orders it before
    # truncating to top_k. RERANKER_BACKEND selects the implementation:
    # "openrouter" calls OpenRouter /v1/rerank (no extra deps; e.g.
    # "cohere/rerank-v3.5"); "local" loads a HuggingFace cross-encoder via
    # torch + sentence-transformers (lazy, e.g. "BAAI/bge-reranker-v2-m3").
    # RERANKER_FALLBACK_MODEL is consulted only on a 402 (out of credits) from
    # the primary model — a :free slug keeps rerank alive when credits run out.
    RERANKER_MODEL: str | None = None
    RERANKER_BACKEND: str = "openrouter"
    RERANKER_FALLBACK_MODEL: str | None = None
    RERANKER_POOL_K: int = 50

    # Training data logging
    TRAINING_DATA_LOGGING_ENABLED: bool = False
    TRAINING_DATA_DEFAULT_ELIGIBLE: bool = False
    TRAINING_DATA_CONSENT_VERSION: str | None = None

    # HTTP Client Connection Pooling
    HTTP_CONNECTION_LIMIT: int = 100  # Max concurrent connections
    HTTP_TIMEOUT_CONNECT: float = 10.0  # Connection timeout in seconds
    HTTP_TIMEOUT_READ: float = 120.0  # Read timeout in seconds (for LLM streaming)
    HTTP_MAX_KEEPALIVE: int = 20  # Max idle connections to keep alive

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )


settings = Settings()
