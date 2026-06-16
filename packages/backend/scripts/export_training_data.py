"""Export structured RAG interaction logs for model training."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.engine import SessionLocal  # noqa: E402
from app.db.models import TrainingRagInteraction  # noqa: E402


def _chunk_map(interaction: TrainingRagInteraction) -> dict[str, dict[str, Any]]:
    return {
        str(chunk["chunk_id"]): dict(chunk)
        for chunk in interaction.retrieved_chunks
        if chunk.get("chunk_id")
    }


def _scrub_chunk(chunk: dict[str, Any], *, anonymize: bool) -> dict[str, Any]:
    cleaned = dict(chunk)
    if anonymize:
        cleaned.pop("pdf_title", None)
    return cleaned


def _embedding_pair_records(
    interactions: list[TrainingRagInteraction],
    *,
    anonymize: bool,
) -> list[dict[str, Any]]:
    records = []
    for interaction in interactions:
        chunks_by_id = _chunk_map(interaction)
        positive_ids = {str(chunk_id) for chunk_id in interaction.cited_chunk_ids or []}
        negatives = [
            _scrub_chunk(chunk, anonymize=anonymize)
            for chunk in interaction.retrieved_chunks
            if chunk.get("included_in_prompt")
            and str(chunk.get("chunk_id")) not in positive_ids
        ]
        for positive_id in positive_ids:
            positive = chunks_by_id.get(positive_id)
            if positive is None:
                continue
            records.append(
                {
                    "query": interaction.query_text,
                    "positive": _scrub_chunk(positive, anonymize=anonymize),
                    "negatives": negatives,
                    "interaction_id": str(interaction.id),
                }
            )
    return records


def _sft_records(
    interactions: list[TrainingRagInteraction],
) -> list[dict[str, Any]]:
    records = []
    for interaction in interactions:
        records.append(
            {
                "messages": [
                    {"role": "system", "content": interaction.system_prompt},
                    *interaction.prompt_messages,
                    {"role": "assistant", "content": interaction.assistant_reply},
                ],
                "interaction_id": str(interaction.id),
                "llm_model": interaction.llm_model,
            }
        )
    return records


def _eval_records(
    interactions: list[TrainingRagInteraction],
    *,
    anonymize: bool,
) -> list[dict[str, Any]]:
    records = []
    for interaction in interactions:
        records.append(
            {
                "query": interaction.query_text,
                "relevant_chunk_ids": [
                    str(chunk_id) for chunk_id in interaction.cited_chunk_ids or []
                ],
                "all_retrieved": [
                    _scrub_chunk(chunk, anonymize=anonymize)
                    for chunk in interaction.retrieved_chunks
                ],
                "interaction_id": str(interaction.id),
            }
        )
    return records


async def _load_interactions(include_ineligible: bool) -> list[TrainingRagInteraction]:
    async with SessionLocal() as db:
        stmt = select(TrainingRagInteraction).order_by(
            TrainingRagInteraction.created_at.asc()
        )
        if not include_ineligible:
            stmt = stmt.where(TrainingRagInteraction.training_eligible.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _write_json(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format",
        choices=("embedding-pairs", "llm-sft", "eval-set"),
        required=True,
    )
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--include-ineligible",
        action="store_true",
        help="Include rows not marked training_eligible; use only for internal diagnostics.",
    )
    parser.add_argument(
        "--anonymize",
        action="store_true",
        help="Strip paper titles from exported chunk metadata.",
    )
    args = parser.parse_args()

    interactions = await _load_interactions(args.include_ineligible)
    if args.format == "embedding-pairs":
        records = _embedding_pair_records(interactions, anonymize=args.anonymize)
        _write_jsonl(Path(args.output), records)
    elif args.format == "llm-sft":
        records = _sft_records(interactions)
        _write_jsonl(Path(args.output), records)
    else:
        records = _eval_records(interactions, anonymize=args.anonymize)
        _write_json(Path(args.output), records)

    print(f"Exported {len(records)} record(s) to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
