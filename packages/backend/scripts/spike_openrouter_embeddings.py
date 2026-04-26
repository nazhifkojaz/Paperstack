"""Phase 0 feasibility spike for the Nemotron embedding migration.

Runs three checks and prints a PASS/FAIL summary:
  0.1  POST /api/v1/embeddings with nvidia/llama-nemotron-embed-vl-1b-v2:free
       → expect HTTP 200, 2048-dim embedding
  0.2  SELECT extversion FROM pg_extension WHERE extname='vector'
       → expect >= 0.7.0 and halfvec(3) cast to succeed
  0.3  GET /api/v1/key
       → record limit / limit_remaining / usage_daily

Reads OPENROUTER_API_KEY and DATABASE_URL from the backend .env via pydantic settings.

Usage (from packages/backend):
    uv run python scripts/spike_openrouter_embeddings.py

Exit code: 0 if all three pass, 1 otherwise.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

EMBED_URL = "https://openrouter.ai/api/v1/embeddings"
KEY_URL = "https://openrouter.ai/api/v1/key"
MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
EXPECTED_DIM = 2048
MIN_PGVECTOR_VERSION = (0, 7, 0)


def _parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".") if p.isdigit())


async def check_embeddings(client: httpx.AsyncClient, api_key: str) -> tuple[bool, str]:
    try:
        resp = await client.post(
            EMBED_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "input": ["This is a test sentence for embedding verification."],
            },
            timeout=30.0,
        )
    except Exception as exc:
        return False, f"request failed: {exc!r}"

    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"

    try:
        data = resp.json()
        embedding = data["data"][0]["embedding"]
    except (KeyError, IndexError, ValueError) as exc:
        return False, f"unexpected response shape: {exc!r} | body={resp.text[:300]}"

    dim = len(embedding)
    if dim != EXPECTED_DIM:
        return False, f"expected {EXPECTED_DIM} dims, got {dim}"

    usage = data.get("usage", {})
    return True, f"dim={dim}, usage={usage}"


async def check_batch_ceiling(client: httpx.AsyncClient, api_key: str) -> tuple[bool, str]:
    """Probe how large a single-request batch the embeddings endpoint accepts.

    Each trial spends 1 request of the daily quota, so we test a short sequence
    rather than bisecting exhaustively. Uses realistic-length inputs (~300 chars)
    so the probe also exercises any per-request token cap.
    """
    trials = [32, 64, 128, 256]
    sample_text = (
        "This is a representative academic sentence of moderate length used to "
        "probe the per-request input ceiling. Repeating this phrase gives us a "
        "realistic payload size per input item during the batch probe. "
    )
    max_passing = 0
    notes: list[str] = []

    for size in trials:
        payload = {"model": MODEL, "input": [sample_text] * size}
        try:
            resp = await client.post(
                EMBED_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60.0,
            )
        except Exception as exc:
            notes.append(f"size={size}: request exception {exc!r}")
            break

        if resp.status_code == 200:
            try:
                returned = len(resp.json()["data"])
            except (KeyError, ValueError):
                returned = -1
            if returned == size:
                max_passing = size
                notes.append(f"size={size}: OK ({returned} embeddings)")
            else:
                notes.append(f"size={size}: returned {returned} (expected {size}); stopping")
                break
        else:
            body = resp.text[:200].replace("\n", " ")
            notes.append(f"size={size}: HTTP {resp.status_code} — {body}")
            break

    if max_passing == 0:
        return False, "no batch size succeeded; " + " | ".join(notes)
    return True, f"max accepted batch={max_passing} | trials: {' | '.join(notes)}"


async def check_pgvector(db_url: str) -> tuple[bool, str]:
    # async engine needs +asyncpg driver; user's DATABASE_URL should already have it
    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
            row = res.first()
            if not row:
                return False, "pgvector extension not installed"
            version_str = row[0]
            version_tuple = _parse_version(version_str)
            if version_tuple < MIN_PGVECTOR_VERSION:
                return False, (
                    f"pgvector {version_str} < required "
                    f"{'.'.join(map(str, MIN_PGVECTOR_VERSION))}"
                )
            try:
                await conn.execute(text("SELECT '[1,2,3]'::halfvec(3)"))
            except Exception as exc:
                return False, f"halfvec cast failed: {exc!r}"
            return True, f"pgvector {version_str}, halfvec cast OK"
    except Exception as exc:
        return False, f"DB connection/query failed: {exc!r}"
    finally:
        await engine.dispose()


async def check_key_limits(client: httpx.AsyncClient, api_key: str) -> tuple[bool, str]:
    try:
        resp = await client.get(
            KEY_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
    except Exception as exc:
        return False, f"request failed: {exc!r}"

    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"

    try:
        data = resp.json()
    except ValueError as exc:
        return False, f"invalid JSON: {exc!r}"

    payload = data.get("data", data)
    limit = payload.get("limit")
    limit_remaining = payload.get("limit_remaining")
    usage_daily = payload.get("usage_daily")
    is_free_tier = payload.get("is_free_tier")

    return True, (
        f"limit={limit} | limit_remaining={limit_remaining} | "
        f"usage_daily={usage_daily} | is_free_tier={is_free_tier}"
    )


async def main() -> int:
    if not settings.OPENROUTER_API_KEY:
        print("FAIL: OPENROUTER_API_KEY is not set in .env")
        return 1
    if not settings.DATABASE_URL:
        print("FAIL: DATABASE_URL is not set in .env")
        return 1

    results: list[tuple[str, bool, str]] = []

    async with httpx.AsyncClient() as client:
        ok, detail = await check_embeddings(client, settings.OPENROUTER_API_KEY)
        results.append(("0.1 embeddings endpoint", ok, detail))

        ok, detail = await check_key_limits(client, settings.OPENROUTER_API_KEY)
        results.append(("0.3 /api/v1/key limits", ok, detail))

        ok, detail = await check_batch_ceiling(client, settings.OPENROUTER_API_KEY)
        results.append(("0.4 batch-size ceiling", ok, detail))

    ok, detail = await check_pgvector(settings.effective_database_url)
    results.append(("0.2 pgvector halfvec", ok, detail))

    print()
    print("=" * 70)
    print("PHASE 0 FEASIBILITY SPIKE RESULTS")
    print("=" * 70)
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        print(f"       {detail}")
    print("=" * 70)

    all_pass = all(ok for _, ok, _ in results)
    print("OVERALL:", "PASS — proceed to Phase 1" if all_pass else "FAIL — halt, update plan")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
