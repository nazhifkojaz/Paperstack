"""
Prompt experimentation script for auto-highlight feature.

Usage:
  python scripts/prompt_experiment.py <pdf_path> --provider glm|gemini --api-key <key>

Evaluates:
  - Quote accuracy (exact match % in source text)
  - Page accuracy
  - JSON validity
  - Category adherence
"""
import argparse
import json
import re
import sys
from pathlib import Path

import httpx
from pypdf import PdfReader

CATEGORY_DEFINITIONS = {
    "findings": "Key results, conclusions, statistical outcomes, novel contributions",
    "methods": "Core experimental design, techniques, key parameters",
    "definitions": "Important terminology, formal definitions, acronyms introduced",
    "limitations": "Stated limitations, caveats, threats to validity, future work",
    "background": "Critical prior work referenced, foundational context",
}

MAX_TEXT_LENGTH = 120_000


def extract_text_with_pages(pdf_path: str) -> tuple[str, int]:
    """Extract text from PDF with page markers. Returns (text, total_pages)."""
    reader = PdfReader(pdf_path)
    parts = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        parts.append(f"--- PAGE {i} ---\n{text}")

    full_text = "\n\n".join(parts)
    if len(full_text) > MAX_TEXT_LENGTH:
        full_text = full_text[:MAX_TEXT_LENGTH]
        print(f"[WARN] Text truncated to {MAX_TEXT_LENGTH} chars")

    return full_text, len(reader.pages)


def build_prompt(text: str, categories: list[str]) -> tuple[str, str]:
    """Build system and user prompts. Returns (system_prompt, user_prompt)."""
    cat_defs = "\n".join(f"- {k}: {v}" for k, v in CATEGORY_DEFINITIONS.items() if k in categories)

    system_prompt = (
        "You are an academic paper analysis assistant. Your task is to identify "
        "the most important passages in a research paper and copy them CHARACTER "
        "FOR CHARACTER from the source text. You are a copy-paste machine — "
        "never rephrase, summarize, or reconstruct what you read."
    )

    user_prompt = f"""Below is the full text of an academic paper. Page boundaries are marked with "--- PAGE {{n}} ---".

Categories to identify: {", ".join(categories)}

Category definitions:
{cat_defs}

Instructions:
1. Read the entire paper carefully
2. Select 10-20 of the most important passages matching the requested categories
3. For each passage, copy the text EXACTLY as it appears — character for character, including spacing and punctuation
4. Identify which page it appears on (look at the nearest "--- PAGE N ---" marker above the passage)
5. Classify it into one of the requested categories
6. Write a brief reason explaining WHY this passage is important

Return a JSON array (no markdown fencing):
[
  {{
    "text": "exact verbatim quote from the paper",
    "page": 1,
    "category": "findings",
    "reason": "This presents the primary result showing X improves Y by Z%"
  }}
]

CRITICAL RULES:
- The "text" field must be a character-for-character copy from the paper text below
- Find the passage in the text, then copy it by selecting and reproducing it exactly
- Do NOT reconstruct from memory — look at the text and copy it
- Do NOT include passages you cannot find verbatim in the text below
- Do not combine sentences from different paragraphs
- Prefer complete sentences (1-3 sentences max per entry)

--- PAPER TEXT ---
{text}"""

    return system_prompt, user_prompt


def call_glm(system_prompt: str, user_prompt: str, api_key: str) -> str:
    """Call Zhipu AI GLM API."""
    resp = httpx.post(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "GLM-4.7-Flash",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_gemini(system_prompt: str, user_prompt: str, api_key: str) -> str:
    """Call Google Gemini API."""
    resp = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        headers={"x-goog-api-key": api_key},
        json={
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.1},
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        text = re.sub(r"^```\w*\n?", "", text)
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def evaluate_response(raw_response: str, source_text: str, categories: list[str]) -> None:
    """Evaluate LLM response quality."""
    cleaned = strip_markdown_fences(raw_response)

    # 1. JSON validity
    try:
        highlights = json.loads(cleaned)
        print(f"[OK] JSON parsed successfully — {len(highlights)} highlights")
    except json.JSONDecodeError:
        # Try sanitizing control characters inside string values
        # (LLMs sometimes embed literal newlines inside JSON strings)
        sanitized = re.sub(r'(?<=[^\\])\n(?=[^"]*")', ' ', cleaned)
        try:
            highlights = json.loads(sanitized)
            print(f"[OK] JSON parsed (after sanitizing control chars) — {len(highlights)} highlights")
        except json.JSONDecodeError as e2:
            print(f"[FAIL] JSON parse error: {e2}")
            print(f"Raw response (first 500 chars): {raw_response[:500]}")
            return

    # 2. Structure validation
    valid = 0
    for i, h in enumerate(highlights):
        missing = [k for k in ("text", "page", "category", "reason") if k not in h]
        if missing:
            print(f"  [WARN] Highlight {i}: missing fields {missing}")
        else:
            valid += 1
    print(f"[OK] Structure: {valid}/{len(highlights)} highlights have all required fields")

    # 3. Quote accuracy (exact match in source)
    exact_matches = 0
    fuzzy_matches = 0
    no_matches = 0
    for h in highlights:
        text = h.get("text", "")
        if text in source_text:
            exact_matches += 1
        elif " ".join(text.split()) in " ".join(source_text.split()):
            fuzzy_matches += 1
        else:
            no_matches += 1
            print(f"  [MISS] Not found: \"{text[:80]}...\"")

    total = len(highlights)
    print(f"[OK] Quote accuracy: {exact_matches}/{total} exact, {fuzzy_matches}/{total} fuzzy, {no_matches}/{total} missed")

    # 4. Category adherence
    valid_cats = set(categories)
    wrong_cat = [h for h in highlights if h.get("category") not in valid_cats]
    if wrong_cat:
        print(f"[WARN] {len(wrong_cat)} highlights with invalid categories: {set(h.get('category') for h in wrong_cat)}")
    else:
        print(f"[OK] All highlights use valid categories")

    # 5. Page range check
    pages = [h.get("page", 0) for h in highlights]
    print(f"[INFO] Page range: {min(pages)}-{max(pages)}")

    # Save results
    output_path = "prompt_experiment_results.json"
    with open(output_path, "w") as f:
        json.dump({"highlights": highlights, "stats": {
            "total": total, "exact_matches": exact_matches,
            "fuzzy_matches": fuzzy_matches, "no_matches": no_matches,
        }}, f, indent=2)
    print(f"\n[SAVED] Results written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Test auto-highlight prompt")
    parser.add_argument("pdf_path", help="Path to PDF file")
    parser.add_argument("--provider", choices=["glm", "gemini"], required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--categories", nargs="+", default=["findings"],
                       choices=list(CATEGORY_DEFINITIONS.keys()))
    args = parser.parse_args()

    print(f"Extracting text from {args.pdf_path}...")
    text, total_pages = extract_text_with_pages(args.pdf_path)
    print(f"Extracted {len(text)} chars from {total_pages} pages")

    print(f"\nBuilding prompt for categories: {args.categories}")
    system_prompt, user_prompt = build_prompt(text, args.categories)

    print(f"Calling {args.provider} API...")
    call_fn = call_glm if args.provider == "glm" else call_gemini
    raw_response = call_fn(system_prompt, user_prompt, args.api_key)

    print(f"\nEvaluating response ({len(raw_response)} chars)...")
    evaluate_response(raw_response, text, args.categories)


if __name__ == "__main__":
    main()
