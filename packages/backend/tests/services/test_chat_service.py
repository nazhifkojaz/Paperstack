"""Tests for ChatService — system prompt invariants.

Locks in the softened grounding instruction (PeerQA ablation: cuts over-refusal
without raising over-answering). Guards against accidental reversion.
"""

from app.services.chat_service import COLLECTION_SYSTEM_PROMPT, SYSTEM_PROMPT

# The strict abstain phrasing that induced over-refusal in the PeerQA study.
_REMOVED_PHRASE = "If the answer is not in the context, say so clearly."
# The softened grounding clause that replaced it.
_SOFTENED_PHRASE = "indirect, partial, or negative"
# The narrower abstain trigger retained by the softened instruction.
_ABSTAIN_PHRASE = "no relevant signal at all"


class TestSystemPrompts:
    def test_system_prompt_drops_over_refusal_clause(self):
        assert _REMOVED_PHRASE not in SYSTEM_PROMPT

    def test_system_prompt_has_softened_grounding(self):
        assert _SOFTENED_PHRASE in SYSTEM_PROMPT
        assert _ABSTAIN_PHRASE in SYSTEM_PROMPT

    def test_system_prompt_keeps_single_pdf_citation_format(self):
        assert "[p.N]" in SYSTEM_PROMPT

    def test_collection_prompt_drops_over_refusal_clause(self):
        assert _REMOVED_PHRASE not in COLLECTION_SYSTEM_PROMPT

    def test_collection_prompt_has_softened_grounding(self):
        assert _SOFTENED_PHRASE in COLLECTION_SYSTEM_PROMPT
        assert _ABSTAIN_PHRASE in COLLECTION_SYSTEM_PROMPT

    def test_collection_prompt_keeps_collection_citation_format(self):
        assert "[Short Title, p.N]" in COLLECTION_SYSTEM_PROMPT
