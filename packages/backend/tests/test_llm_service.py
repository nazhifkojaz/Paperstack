import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.llm_service import (
    LLMService, parse_llm_response, build_prompt, strip_markdown_fences,
    CATEGORY_COLORS,
)


def test_strip_markdown_fences_json():
    raw = '```json\n[{"text": "hello", "page": 1, "category": "findings", "reason": "test"}]\n```'
    assert strip_markdown_fences(raw) == '[{"text": "hello", "page": 1, "category": "findings", "reason": "test"}]'


def test_strip_markdown_fences_no_fence():
    raw = '[{"text": "hello"}]'
    assert strip_markdown_fences(raw) == '[{"text": "hello"}]'


def test_strip_markdown_fences_plain_backticks():
    raw = '```\n[{"text": "x"}]\n```'
    assert strip_markdown_fences(raw) == '[{"text": "x"}]'


def test_parse_llm_response_valid():
    raw = json.dumps([
        {"text": "Some finding", "page": 1, "category": "findings", "reason": "Important result"},
        {"text": "A method", "page": 3, "category": "methods", "reason": "Core technique"},
    ])
    highlights = parse_llm_response(raw)
    assert len(highlights) == 2
    assert highlights[0]["text"] == "Some finding"
    assert highlights[0]["category"] == "findings"


def test_parse_llm_response_with_fences():
    raw = '```json\n[{"text": "x", "page": 1, "category": "findings", "reason": "y"}]\n```'
    highlights = parse_llm_response(raw)
    assert len(highlights) == 1


def test_parse_llm_response_invalid_json():
    with pytest.raises(ValueError, match="Failed to parse"):
        parse_llm_response("not json at all")


def test_parse_llm_response_missing_fields():
    raw = json.dumps([{"text": "hello"}])  # missing page, category, reason
    highlights = parse_llm_response(raw)
    assert len(highlights) == 1
    assert highlights[0]["page"] == 0
    assert highlights[0]["category"] == "unknown"
    assert highlights[0]["reason"] == ""


def test_parse_llm_response_not_list():
    raw = json.dumps({"text": "not a list"})
    with pytest.raises(ValueError, match="Expected JSON array"):
        parse_llm_response(raw)


def test_build_prompt_contains_categories():
    system, user = build_prompt("Some paper text", ["findings", "methods"])
    assert "findings" in user
    assert "methods" in user
    assert "EXACT" in system or "character" in system.lower()
    assert "Some paper text" in user


def test_build_prompt_only_selected_categories():
    system, user = build_prompt("text", ["findings"])
    assert "findings" in user
    assert "limitations" not in user


def test_category_colors():
    assert "findings" in CATEGORY_COLORS
    assert "methods" in CATEGORY_COLORS
    assert "definitions" in CATEGORY_COLORS
    assert "limitations" in CATEGORY_COLORS
    assert "background" in CATEGORY_COLORS
    for color in CATEGORY_COLORS.values():
        assert color.startswith("#")
        assert len(color) == 7


@pytest.mark.asyncio
async def test_llm_service_analyze_paper_glm():
    service = LLMService()
    mock_response = json.dumps([
        {"text": "Key result", "page": 1, "category": "findings", "reason": "Primary finding"},
    ])
    with patch.object(service, "call_glm", new=AsyncMock(return_value=mock_response)):
        highlights = await service.analyze_paper("paper text", ["findings"], "glm", "fake-key")
    assert len(highlights) == 1
    assert highlights[0]["text"] == "Key result"


@pytest.mark.asyncio
async def test_llm_service_analyze_paper_gemini():
    service = LLMService()
    mock_response = json.dumps([
        {"text": "A method", "page": 2, "category": "methods", "reason": "Core approach"},
    ])
    with patch.object(service, "call_gemini", new=AsyncMock(return_value=mock_response)):
        highlights = await service.analyze_paper("paper text", ["methods"], "gemini", "fake-key")
    assert len(highlights) == 1
    assert highlights[0]["category"] == "methods"


@pytest.mark.asyncio
async def test_llm_service_unknown_provider():
    service = LLMService()
    with pytest.raises(ValueError, match="Unknown provider"):
        await service.analyze_paper("text", ["findings"], "openai", "key")
