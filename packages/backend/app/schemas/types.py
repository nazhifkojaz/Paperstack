from typing import TypedDict


class ChatMessageDict(TypedDict):
    role: str
    content: str


class ChunkDict(TypedDict, total=False):
    content: str
    page_number: int
    end_page_number: int
    section_title: str
    section_level: int


class PaperMetadata(TypedDict, total=False):
    title: str
    authors: str
    year: int


class ContextChunkDict(TypedDict):
    chunk_id: str
    page_number: int
    snippet: str


class HighlightDict(TypedDict):
    text: str
    page: int
    category: str
    reason: str


class AnnotationExportDict(TypedDict):
    page_number: int
    type: str
    color: str
    rects: list[dict[str, float]]
