"""SEC filing HTML → docling document → token-bounded chunks with page and section.

HybridChunker runs docling's HierarchicalChunker (one chunk per element, with its
headings) and then splits/merges the result against the embedding model's tokenizer.
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import tiktoken
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.transforms.serializer.markdown import MarkdownTableSerializer
from docling_core.types.doc import (
    DoclingDocument,
    SectionHeaderItem,
    TableItem,
    TextItem,
    TitleItem,
)

from app.config import settings

# Target size for the embedded text (headings + chunk); smaller chunks retrieve and
# cite better than the model's 8191-token limit, which load_chunks enforces. Split
# tables can overshoot by the heading length: docling's row-wise table splitter
# budgets the repeated header row but not the heading prefix.
MAX_TOKENS = 512

# EDGAR filings mark printed page boundaries with <hr style="page-break-after:always">.
PAGE_BREAK = re.compile(r"<hr\b[^>]*page-break-after\s*:\s*always[^>]*>", re.IGNORECASE)
PAGE_MARKER = re.compile(r"THESISLENS-PAGE-(\d+)")
# Layout tables and image placeholders produce chunks with no actual prose.
TWO_WORDS = re.compile(r"[A-Za-z]{2,}\W+[A-Za-z]{2,}")
# Form 10-K section titles are fixed by the SEC but styled as bold text, not <h*> tags,
# so docling sees no headings. Length caps keep prose that starts with "Item 7." out.
PART_HEADING = re.compile(r"PART\s+(IV|I{1,3})\b.{0,60}", re.IGNORECASE)
PART_NUMBERS = {"I": 1, "II": 2, "III": 3, "IV": 4}
ITEM_HEADING = re.compile(r"ITEM\s+\d{1,2}[A-C]?\..{0,200}", re.IGNORECASE)


@dataclass
class Chunk:
    index: int
    content: str
    embed_text: str
    headings: list[str]
    page: int | None
    page_end: int | None
    token_count: int

    @property
    def section(self) -> str | None:
        return " > ".join(self.headings) or None


class MarkdownTableSerializerProvider(ChunkingSerializerProvider):
    """Serialize tables as Markdown rather than docling's default "row, col = value" triplets.

    Financial tables stay readable in citations, and HybridChunker can repeat the
    header row on every piece of a split table.
    """

    def get_serializer(self, doc: DoclingDocument) -> ChunkingDocSerializer:
        return ChunkingDocSerializer(doc=doc, table_serializer=MarkdownTableSerializer())


@cache
def get_chunker() -> HybridChunker:
    encoding = tiktoken.encoding_for_model(settings.openai_embedding_model)
    return HybridChunker(
        tokenizer=OpenAITokenizer(tokenizer=encoding, max_tokens=MAX_TOKENS),
        serializer_provider=MarkdownTableSerializerProvider(),
    )


def insert_page_markers(html: str) -> str:
    """Replace each page break with a paragraph naming the page that follows it."""
    next_page = iter(range(2, 1_000_000))
    return PAGE_BREAK.sub(lambda _: f"<p>THESISLENS-PAGE-{next(next_page)}</p>", html)


def parse_html(html: str, name: str) -> DoclingDocument:
    converter = DocumentConverter(allowed_formats=[InputFormat.HTML])
    return converter.convert_string(insert_page_markers(html), InputFormat.HTML, name=name).document


def heading_text(item: object) -> str | None:
    """The PART/Item heading this item stands for, if any."""
    # Real <h*> headings are already sections; deleting one would also delete its children.
    if isinstance(item, SectionHeaderItem | TitleItem):
        return None
    if isinstance(item, TextItem):
        text = " ".join(item.text.split())
    elif isinstance(item, TableItem):
        # Some filers (e.g. Amazon) lay out "Item 1A. | Risk Factors" as a table with one
        # real row (plus empty spacer rows); multi-row tables are the table of contents.
        rows = [[" ".join(cell.text.split()) for cell in row] for row in item.data.grid]
        rows = [row for row in rows if any(row)]
        if len(rows) != 1:
            return None
        text = " ".join(dict.fromkeys(cell for cell in rows[0] if cell))
    else:
        return None
    if PART_HEADING.fullmatch(text) or ITEM_HEADING.fullmatch(text):
        return text
    return None


def promote_headings(doc: DoclingDocument) -> None:
    """Turn 10-K PART (level 1) and Item (level 2) titles into section headers.

    PARTs only move forward in a filing, so a lower PART after a higher one means
    everything matched so far was the table of contents; those lines stay plain text.
    Repeats of the current PART are running page headers and are dropped: promoting
    them would reset the Item heading on every page.
    """
    headings: list[tuple[TextItem | TableItem, str, int]] = []
    running_headers: list[TextItem | TableItem] = []
    part = 0
    for item, _ in doc.iterate_items():
        text = heading_text(item)
        if text is None:
            continue
        if match := PART_HEADING.fullmatch(text):
            number = PART_NUMBERS[match[1].upper()]
            if number == part:
                running_headers.append(item)
                continue
            if number < part:
                headings, running_headers = [], []
            part = number
            headings.append((item, text, 1))
        else:
            headings.append((item, text, 2))

    # Mutate only after collecting: inserting while iterating would shift the traversal.
    for item, text, level in headings:
        doc.insert_heading(sibling=item, text=text, level=level, after=False)
    replaced = [item for item, _, _ in headings] + running_headers
    if replaced:
        doc.delete_items(node_items=replaced)


def extract_pages(doc: DoclingDocument) -> dict[str, int]:
    """Remove the page markers from `doc` and return each remaining item's page, by self_ref."""
    page_by_item: dict[int, int] = {}
    markers = []
    page = 1
    for item, _ in doc.iterate_items():
        if isinstance(item, TextItem) and (match := PAGE_MARKER.fullmatch(item.text.strip())):
            page = int(match[1])
            markers.append(item)
        else:
            page_by_item[id(item)] = page
    if markers:
        doc.delete_items(node_items=markers)
    # Deleting renumbers self_refs (#/texts/N), so key the map only after deleting.
    return {
        item.self_ref: page_by_item[id(item)]
        for item, _ in doc.iterate_items()
        if id(item) in page_by_item
    }


def chunk_document(doc: DoclingDocument, pages: dict[str, int]) -> list[Chunk]:
    chunker = get_chunker()
    chunks = []
    for raw in chunker.chunk(doc):
        if not TWO_WORDS.search(raw.text):
            continue
        item_pages = [pages[item.self_ref] for item in raw.meta.doc_items if item.self_ref in pages]
        embed_text = chunker.contextualize(raw)
        chunks.append(
            Chunk(
                index=len(chunks),
                content=raw.text,
                embed_text=embed_text,
                headings=raw.meta.headings or [],
                page=min(item_pages, default=None),
                page_end=max(item_pages, default=None),
                token_count=chunker.tokenizer.count_tokens(embed_text),
            )
        )
    return chunks


def prepare_document(html: str, name: str) -> tuple[DoclingDocument, dict[str, int]]:
    """Parse a filing, promote its 10-K headings, and map items to pages.

    Headings go first: both steps delete items, and the page map is keyed by the
    self_refs that remain after the last deletion.
    """
    doc = parse_html(html, name)
    promote_headings(doc)
    return doc, extract_pages(doc)


def chunk_filing(path: Path) -> list[Chunk]:
    return chunk_document(*prepare_document(path.read_text(encoding="utf-8"), name=path.stem))
