"""Tests for the contextualizer (Contextual Retrieval)."""

from dataclasses import dataclass

from app.services.contextualizer import build_embed_inputs, build_embedding_text


@dataclass
class _ChunkStub:
    """Minimal chunk-like object for testing build_embed_inputs."""

    content: str
    section_title: str | None = None


class TestBuildEmbeddingText:
    def test_prepends_paper_and_section(self):
        result = build_embedding_text(
            content="The model achieves 95% accuracy.",
            pdf_title="Attention Is All You Need",
            section_title="Results",
        )
        assert result == (
            "Paper: Attention Is All You Need\n"
            "Section: Results\n\n"
            "The model achieves 95% accuracy."
        )

    def test_uses_untitled_when_section_none(self):
        result = build_embedding_text(
            content="Body text.",
            pdf_title="Some Paper",
            section_title=None,
        )
        assert result == (
            "Paper: Some Paper\n"
            "Section: (untitled)\n\n"
            "Body text."
        )

    def test_uses_untitled_when_section_blank(self):
        result = build_embedding_text(
            content="Body text.",
            pdf_title="Some Paper",
            section_title="   ",
        )
        assert "Section: (untitled)" in result

    def test_strips_whitespace_from_section(self):
        result = build_embedding_text(
            content="Body text.",
            pdf_title="Some Paper",
            section_title="  Methods  ",
        )
        assert "Section: Methods\n\n" in result

    def test_preserves_raw_content_verbatim(self):
        body = "Multi-line\nbody\nwith  weird   spacing."
        result = build_embedding_text(
            content=body,
            pdf_title="P",
            section_title="S",
        )
        assert result.endswith(body)

    def test_empty_content_still_gets_header(self):
        result = build_embedding_text(
            content="",
            pdf_title="P",
            section_title="S",
        )
        assert result == "Paper: P\nSection: S\n\n"

    def test_pdf_title_used_verbatim(self):
        # Titles with colons, parentheses, unicode should pass through unchanged.
        result = build_embedding_text(
            content="x",
            pdf_title="On the Paradox of (Self-)Reference: A Survey",
            section_title="Discussion",
        )
        assert "Paper: On the Paradox of (Self-)Reference: A Survey\n" in result


class TestBuildEmbedInputs:
    def _chunks(self):
        return [
            _ChunkStub(content="First body.", section_title="Intro"),
            _ChunkStub(content="Second body.", section_title=None),
        ]

    def test_returns_one_input_per_chunk_in_order(self):
        chunks = self._chunks()
        result = build_embed_inputs(chunks, "Paper", contextualize=False)
        assert [c.content for c in chunks] == result

    def test_contextualize_true_prefixes_each_chunk(self):
        chunks = self._chunks()
        result = build_embed_inputs(chunks, "My Paper", contextualize=True)
        assert result[0] == "Paper: My Paper\nSection: Intro\n\nFirst body."
        assert result[1] == "Paper: My Paper\nSection: (untitled)\n\nSecond body."

    def test_contextualize_false_returns_raw_content(self):
        chunks = [_ChunkStub(content="Raw text.", section_title="Methods")]
        result = build_embed_inputs(chunks, "Ignored", contextualize=False)
        assert result == ["Raw text."]

    def test_strips_null_bytes_from_embedded_text(self):
        """Regression: \\x00 must be stripped before embedding, matching
        what is persisted to the `content` column."""
        chunks = [_ChunkStub(content="A\x00B", section_title="S")]
        result = build_embed_inputs(chunks, "P", contextualize=True)
        assert result == ["Paper: P\nSection: S\n\nAB"]

    def test_strips_null_bytes_even_when_not_contextualizing(self):
        chunks = [_ChunkStub(content="A\x00B")]
        result = build_embed_inputs(chunks, "P", contextualize=False)
        assert result == ["AB"]

    def test_empty_chunk_list_returns_empty_list(self):
        assert build_embed_inputs([], "P", contextualize=True) == []
