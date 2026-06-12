import uuid
from types import SimpleNamespace

from scripts.export_training_data import (
    _embedding_pair_records,
    _eval_records,
    _sft_records,
)


def _interaction():
    positive_id = uuid.uuid4()
    negative_id = uuid.uuid4()
    excluded_id = uuid.uuid4()
    return SimpleNamespace(
        id=uuid.uuid4(),
        query_text="What is attention?",
        cited_chunk_ids=[positive_id],
        retrieved_chunks=[
            {
                "chunk_id": str(positive_id),
                "pdf_title": "Attention Is All You Need",
                "content": "positive chunk",
                "included_in_prompt": True,
            },
            {
                "chunk_id": str(negative_id),
                "pdf_title": "Attention Is All You Need",
                "content": "negative chunk",
                "included_in_prompt": True,
            },
            {
                "chunk_id": str(excluded_id),
                "pdf_title": "Attention Is All You Need",
                "content": "not sent to prompt",
                "included_in_prompt": False,
            },
        ],
        system_prompt="system",
        prompt_messages=[{"role": "user", "content": "What is attention?"}],
        assistant_reply="It is a mechanism.",
        llm_model="test-model",
    )


def test_embedding_pair_records_use_cited_chunks_as_positives():
    interaction = _interaction()

    records = _embedding_pair_records([interaction], anonymize=True)

    assert len(records) == 1
    assert records[0]["query"] == "What is attention?"
    assert records[0]["positive"]["content"] == "positive chunk"
    assert "pdf_title" not in records[0]["positive"]
    assert [chunk["content"] for chunk in records[0]["negatives"]] == [
        "negative chunk"
    ]


def test_sft_records_include_prompt_and_assistant_messages():
    interaction = _interaction()

    records = _sft_records([interaction])

    assert records == [
        {
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "What is attention?"},
                {"role": "assistant", "content": "It is a mechanism."},
            ],
            "interaction_id": str(interaction.id),
            "llm_model": "test-model",
        }
    ]


def test_eval_records_preserve_all_retrieved_chunks():
    interaction = _interaction()

    records = _eval_records([interaction], anonymize=False)

    assert records[0]["query"] == "What is attention?"
    assert records[0]["relevant_chunk_ids"] == [
        str(interaction.cited_chunk_ids[0])
    ]
    assert [chunk["content"] for chunk in records[0]["all_retrieved"]] == [
        "positive chunk",
        "negative chunk",
        "not sent to prompt",
    ]
