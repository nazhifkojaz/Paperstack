"""Test configuration for Paperstack backend tests.

Uses PostgreSQL via testcontainers to match production behavior.
"""
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Generator
import uuid

import pytest
import pytest_asyncio
import respx
from httpx import AsyncClient, ASGITransport, Response
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from testcontainers.postgres import PostgresContainer

from app.main import app
from app.db.models import Base, User
from app.core.security import create_access_token, create_refresh_token


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Start a PostgreSQL container with pgvector for the test session.

    This container is reused across all tests for speed.
    """
    # Use pgvector-enabled image and enable the extension
    with PostgresContainer("pgvector/pgvector:pg16") as postgres:
        # Wait for the container to be ready
        postgres.get_connection_url()
        yield postgres


@pytest.fixture(scope="session")
def test_engine(postgres_container: PostgresContainer):
    """Create a SQLAlchemy engine connected to the test container."""
    import asyncio
    from sqlalchemy.pool import NullPool

    connection_url = postgres_container.get_connection_url()
    # Convert postgresql+psycopg2:// to postgresql+asyncpg:// for async SQLAlchemy
    async_url = connection_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    async_url = async_url.replace("postgresql://", "postgresql+asyncpg://")

    # Use NullPool to avoid connection sharing issues across tests
    # Each test will get its own fresh connection
    engine = create_async_engine(
        async_url,
        echo=False,
        poolclass=NullPool,
    )
    yield engine

    # Dispose the engine synchronously (create_async_engine returns a regular object)
    # The disposal will be handled when the engine is garbage collected
    # or we can run it in an event loop if needed


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test.

    Creates all tables before the test and drops them after.
    """
    async with test_engine.begin() as conn:
        # Create pgvector extension first (required for Vector columns)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session

    # Clean up - drop all tables after test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create an HTTP test client with database dependency override."""
    from app.api import deps

    async def override_get_db():
        yield db_session

    app.dependency_overrides[deps.get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides = {}


@pytest_asyncio.fixture
async def admin_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create an authenticated HTTP client with admin user."""
    from app.api import deps
    from app.core import security

    now = datetime.now(timezone.utc)
    admin_user = User(
        github_id=999999,
        github_login="admin",
        display_name="Admin User",
        avatar_url="https://example.com/admin.png",
        access_token=security.encrypt_token("gh_admin_token"),
        created_at=now,
        updated_at=now,
    )
    db_session.add(admin_user)
    await db_session.commit()
    await db_session.refresh(admin_user)

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return admin_user

    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[deps.get_current_user] = override_get_current_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides = {}


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user in the database."""
    from app.core import security

    now = datetime.now(timezone.utc)
    user = User(
        github_id=123456,
        github_login="testuser",
        display_name="Test User",
        avatar_url="https://example.com/avatar.png",
        access_token=security.encrypt_token("gh_test_token"),
        created_at=now,
        updated_at=now,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_user_2(db_session: AsyncSession) -> User:
    """Create a second test user in the database."""
    from app.core import security

    now = datetime.now(timezone.utc)
    user = User(
        github_id=789012,
        github_login="testuser2",
        display_name="Second User",
        avatar_url="https://example.com/avatar2.png",
        access_token=security.encrypt_token("gh_test_token_2"),
        created_at=now,
        updated_at=now,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    """Create authentication headers for the test user."""
    access_token = create_access_token(test_user.id)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def auth_headers_2(test_user_2: User) -> dict[str, str]:
    """Create authentication headers for the second test user."""
    access_token = create_access_token(test_user_2.id)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def expired_token(test_user: User) -> str:
    """Create an expired JWT token for testing."""
    from jose import jwt
    from app.core.security import SECRET_KEY, ALGORITHM

    expire = datetime.now(timezone.utc) - timedelta(hours=1)
    to_encode = {
        "exp": expire,
        "sub": str(test_user.id),
        "type": "access"
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@pytest.fixture
def invalid_token() -> str:
    """Return an invalid token string."""
    return "invalid.token.here"


@pytest.fixture
def mock_github_api() -> Generator[respx.MockRouter, None, None]:
    """Mock GitHub API responses for testing."""
    respx.start()

    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=Response(
            200,
            json={"access_token": "gh_test_token", "token_type": "bearer"},
        )
    )

    respx.get("https://api.github.com/user").mock(
        return_value=Response(
            200,
            json={
                "id": 123456,
                "login": "testuser",
                "name": "Test User",
                "email": "test@example.com",
                "avatar_url": "https://example.com/avatar.png",
            },
        )
    )

    respx.get("https://api.github.com/repos/testuser/paperstack-library").mock(
        return_value=Response(404, json={"message": "Not Found"})
    )

    respx.post("https://api.github.com/user/repos").mock(
        return_value=Response(
            201,
            json={
                "name": "paperstack-library",
                "full_name": "testuser/paperstack-library",
                "html_url": "https://github.com/testuser/paperstack-library",
            },
        )
    )

    # Mock GET requests for PDF content from GitHub API
    # When Accept header is application/vnd.github.v3.raw, return raw PDF bytes
    def side_effect_get_pdf(request):
        if "application/vnd.github.v3.raw" in request.headers.get("accept", ""):
            # Return valid minimal PDF
            return Response(
                200,
                content=b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
200
%%EOF
""",
            )
        else:
            # Return JSON metadata response
            return Response(
                200,
                json={"content": {"sha": "abc123def456", "name": "test.pdf"}},
            )

    respx.get(host__regex=r"api\.github\.com", path__regex=r"/repos/.*contents/.*").mock(side_effect=side_effect_get_pdf)

    # Mock PUT requests for uploading PDFs
    respx.put(host__regex=r"api\.github\.com", path__regex=r"/repos/.*contents/.*").mock(
        return_value=Response(
            201,
            json={"content": {"sha": "abc123def456", "name": "test.pdf"}},
        )
    )

    respx.route(host__regex=r"raw\.githubusercontent\.com", path__regex=r"/.*\.pdf").mock(
        return_value=Response(
            200,
            content=b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
200
%%EOF
""",
        )
    )

    respx.delete(host__regex=r"api\.github\.com").mock(
        return_value=Response(200)
    )

    yield respx
    respx.stop()


@pytest.fixture
def mock_crossref_api() -> Generator[respx.MockRouter, None, None]:
    """Mock CrossRef API responses for testing."""
    respx.start()

    # Mock both content types using a single side_effect that checks Accept header
    def side_effect_combined(request):
        accept_header = request.headers.get("Accept", "")
        if "10.1234/test.doi.12345" in request.url.path:
            # BibTeX content negotiation
            if "application/x-bibtex" in accept_header:
                return Response(
                    200,
                    text='@article{test2024,\n  title = {Test Paper Title},\n  author = {Doe, John and Smith, Jane},\n  year = {2024}\n}'
                )
            # CSL-JSON content negotiation (default)
            return Response(
                200,
                json={
                    "title": ["Test Paper Title"],
                    "author": [
                        {"given": "John", "family": "Doe"},
                        {"given": "Jane", "family": "Smith"},
                    ],
                    "issued": {"date-parts": [[2024, 1, 1]]},
                    "type": "journal-article",
                }
            )
        # Not found for other DOIs
        return Response(404, text="Not Found")

    respx.route(host__regex=r"doi\.org").mock(side_effect=side_effect_combined)

    yield respx
    respx.stop()


@pytest.fixture
def mock_openlibrary_api() -> Generator[respx.MockRouter, None, None]:
    """Mock Open Library API responses for testing."""
    respx.start()

    # Successful book lookup - use URL pattern for specificity
    respx.get("https://openlibrary.org/api/books").mock(
        return_value=Response(
            200,
            json={
                "ISBN:0262033844": {
                    "title": "Introduction to Algorithms",
                    "authors": [{"name": "Thomas H. Cormen"}],
                    "publish_date": "2009",
                    "publishers": [{"name": "MIT Press"}]
                }
            },
        )
    )

    yield respx
    respx.stop()


@pytest.fixture
def mock_openlibrary_api_not_found() -> Generator[respx.MockRouter, None, None]:
    """Mock Open Library API for not found responses."""
    respx.start()

    # Empty response means not found (Open Library returns 200 with empty dict)
    respx.get("https://openlibrary.org/api/books").mock(
        return_value=Response(200, json={})
    )

    yield respx
    respx.stop()


@pytest.fixture
def mock_crossref_api_not_found() -> Generator[respx.MockRouter, None, None]:
    """Mock CrossRef API for not found responses."""
    respx.start()

    # Mock both BibTeX and JSON content negotiation to return 404
    respx.get("https://doi.org/10.9999/nonexistent").mock(
        return_value=Response(404, text="Not Found")
    )

    yield respx
    respx.stop()


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Generate a minimal valid PDF for testing."""
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Count 1\n/Kids [3 0 R]\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n210\n%%EOF"


@pytest.fixture
def sample_bibtex() -> str:
    """Return a sample BibTeX citation string."""
    return '@article{test2024, title={Test Paper Title}, author={Doe, John}, journal={Journal of Tests}, year={2024}}'


@pytest.fixture(autouse=True)
def set_test_env_vars(monkeypatch) -> None:
    """Set required environment variables for all tests."""
    # These will be overridden by the actual database connection
    monkeypatch.setenv("JWT_SECRET", "test_secret_for_jwt_signing")
    monkeypatch.setenv("ENCRYPTION_KEY", "test_encryption_key_32_bytes_long")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test_github_client_id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test_github_client_secret")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:5173/Paperstack")
