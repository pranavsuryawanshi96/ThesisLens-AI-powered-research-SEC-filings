from docling_core.types.doc import TextItem

from ingest.chunking import (
    MAX_TOKENS,
    chunk_document,
    extract_pages,
    get_chunker,
    insert_page_markers,
    parse_html,
    prepare_document,
)

LONG_PARAGRAPH = " ".join(f"Services revenue grew in region {i} due to subscriptions." for i in range(400))

FILING_HTML = f"""
<html><body>
<h1>Item 1. Business</h1>
<p>The Company designs, manufactures and markets smartphones and personal computers.</p>
<hr style="page-break-after:always"/>
<h2>Products</h2>
<p>iPhone is the Company's line of smartphones based on its iOS operating system.</p>
<table><tr><td></td><td></td></tr></table>
<p>g66145g66i43.jpg</p>
<hr style="margin-inline-start:auto;page-break-after:always;"/>
<h1>Item 7. Management's Discussion and Analysis</h1>
<p>{LONG_PARAGRAPH}</p>
</body></html>
"""


def chunks_for(html: str):
    return chunk_document(*prepare_document(html, name="test"))


BREAK = '<hr style="page-break-after:always"/>'
CROSS_REFERENCE = (
    "Item 7. of this report describes how net sales are recognized, and this sentence keeps "
    "going well past any real heading length so that it reads as ordinary prose in the filing "
    "and must stay a paragraph instead of being promoted into a section heading of its own."
)
TEN_K_HTML = f"""
<html><body>
<table>
  <tr><td>Item 1A.</td><td><a href="#risk">Risk Factors</a></td><td>6</td></tr>
  <tr><td>Item 7.</td><td><a href="#mdna">Management's Discussion</a></td><td>22</td></tr>
</table>
<p>Part I</p>
<p>Item 1A.</p>
<p>Part II</p>
<p>Item 7.</p>
<p>This report contains forward-looking statements about future events and results.</p>
{BREAK}
<p><span style="font-weight:bold">PART I</span></p>
<p><span style="font-weight:bold">Item 1A. Risk Factors</span></p>
<p>Supply chain disruptions could adversely affect the Company's operating results.</p>
{BREAK}
<p>PART I</p>
<p>Competition in smartphone markets remains intense and pricing pressure continues.</p>
<p>{CROSS_REFERENCE}</p>
{BREAK}
<p><span style="font-weight:bold">PART II</span></p>
<table>
  <tr><td></td><td></td><td></td></tr>
  <tr><td>Item 7.</td><td>Management's Discussion</td><td>Management's Discussion</td></tr>
</table>
<p>Total net sales increased two percent compared with the prior fiscal year.</p>
</body></html>
"""


def chunk_containing(chunks, text: str):
    return next(c for c in chunks if text in c.content)


def test_10k_part_and_item_titles_become_sections():
    chunks = chunks_for(TEN_K_HTML)

    assert chunk_containing(chunks, "Supply chain").section == "PART I > Item 1A. Risk Factors"
    assert chunk_containing(chunks, "Total net sales").section == "PART II > Item 7. Management's Discussion"


def test_running_part_header_is_dropped_without_resetting_the_item():
    chunks = chunks_for(TEN_K_HTML)

    competition = chunk_containing(chunks, "Competition in smartphone")
    assert competition.section == "PART I > Item 1A. Risk Factors"
    assert competition.page <= 3 <= competition.page_end
    assert not any(c.content.strip().startswith("PART I\n") for c in chunks)


def test_table_of_contents_and_long_cross_references_are_not_headings():
    chunks = chunks_for(TEN_K_HTML)

    toc = chunk_containing(chunks, "(#risk)")
    assert toc.headings == []
    # Plain-line tables of contents (Apple, Nvidia) must not leak "Part II > Item 7."
    assert chunk_containing(chunks, "forward-looking statements").headings == []
    assert chunk_containing(chunks, "of this report describes").section == "PART I > Item 1A. Risk Factors"


def test_insert_page_markers_numbers_pages_after_each_break():
    html = insert_page_markers('<p>a</p><hr style="page-break-after:always"/><p>b</p><HR STYLE="PAGE-BREAK-AFTER: always"><p>c</p>')
    assert html == "<p>a</p><p>THESISLENS-PAGE-2</p><p>b</p><p>THESISLENS-PAGE-3</p><p>c</p>"


def test_insert_page_markers_ignores_plain_rules():
    assert insert_page_markers("<hr/><p>a</p>") == "<hr/><p>a</p>"


def test_extract_pages_removes_markers_and_maps_items():
    doc = parse_html(FILING_HTML, name="test")
    pages = extract_pages(doc)

    texts = {item.text: pages[item.self_ref] for item, _ in doc.iterate_items() if isinstance(item, TextItem)}
    assert not any("THESISLENS-PAGE" in text for text in texts)
    assert texts["Item 1. Business"] == 1
    assert texts["Products"] == 2
    assert texts["Item 7. Management's Discussion and Analysis"] == 3


def test_chunks_carry_page_and_section():
    chunks = chunks_for(FILING_HTML)

    iphone = next(c for c in chunks if "iPhone" in c.content)
    assert iphone.page == 2
    assert iphone.section is not None and "Products" in iphone.section

    mdna = [c for c in chunks if "Services revenue" in c.content]
    assert mdna and all(c.page == 3 for c in mdna)
    assert all(c.headings[-1] == "Item 7. Management's Discussion and Analysis" for c in mdna)


def test_chunks_respect_token_limit_including_headings():
    chunks = chunks_for(FILING_HTML)

    long_section = [c for c in chunks if "Services revenue" in c.content]
    assert len(long_section) > 1
    tokenizer = get_chunker().tokenizer
    for chunk in chunks:
        assert chunk.token_count == tokenizer.count_tokens(chunk.embed_text)
        assert chunk.token_count <= MAX_TOKENS


def test_embed_text_prefixes_headings_to_content():
    chunk = next(c for c in chunks_for(FILING_HTML) if "iPhone" in c.content)
    assert chunk.embed_text.startswith(chunk.headings[0])
    assert chunk.embed_text.endswith(chunk.content)


def test_large_tables_split_as_markdown_with_repeated_header():
    rows = "".join(f"<tr><td>Product line {i}</td><td>{i * 1000}</td></tr>" for i in range(300))
    html = (
        "<html><body><h1>Net Sales by Category</h1><table>"
        f"<tr><th>Category</th><th>Net sales</th></tr>{rows}</table></body></html>"
    )

    table_chunks = [c for c in chunks_for(html) if "Product line" in c.content]

    assert len(table_chunks) > 1
    heading_tokens = get_chunker().tokenizer.count_tokens("Net Sales by Category\n")
    for chunk in table_chunks:
        assert chunk.content.lstrip().startswith("| Category")
        assert "= " not in chunk.content  # not docling's triplet notation
        # docling's row-wise table split budgets the header row but not the heading.
        assert chunk.token_count <= MAX_TOKENS + heading_tokens


def test_junk_chunks_are_dropped_and_indexes_stay_contiguous():
    chunks = chunks_for(FILING_HTML)

    assert not any("g66145g66i43.jpg" == c.content.strip() for c in chunks)
    assert all(any(ch.isalpha() for ch in c.content) for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
