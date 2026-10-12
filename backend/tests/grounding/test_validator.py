from uuid import uuid4

import pytest

from app.assistant.outputs import Citation, GroundedAnswer
from app.grounding.validator import marker_indexes, validate_grounding


@pytest.fixture
def passage(make_passage):
    return make_passage()


@pytest.fixture
def retrieved(passage):
    return {passage.chunk_id: passage}


def answer(text: str, *citations: Citation, status: str = "answered") -> GroundedAnswer:
    return GroundedAnswer(status=status, answer=text, citations=list(citations))


def cite(passage, quote: str, index: int = 1) -> Citation:
    return Citation(index=index, chunk_id=passage.chunk_id, quote=quote)


def test_grounded_answer_passes(passage, retrieved):
    result = answer(
        "iPhone net sales were $201,183 million in 2024 [1] and roughly flat year over year [2].",
        cite(passage, "iPhone | $ 201,183", 1),
        cite(passage, "iPhone net sales were relatively flat during 2024", 2),
    )

    assert validate_grounding(result, retrieved) == []


def test_answered_without_citations_fails(retrieved):
    errors = validate_grounding(answer("Apple sells phones."), retrieved)

    assert any("at least one citation" in e for e in errors)


@pytest.mark.parametrize("status", ["insufficient_evidence", "out_of_scope"])
def test_non_answers_may_have_no_citations(status, retrieved):
    assert validate_grounding(answer("The filings do not say.", status=status), retrieved) == []


def test_insufficient_evidence_citations_are_still_checked(passage, retrieved):
    result = answer(
        "The filings only report iPhone sales [1].",
        cite(passage, "iPhone sales grew 40% because of AI"),
        status="insufficient_evidence",
    )

    assert validate_grounding(result, retrieved)


def test_citing_a_chunk_not_retrieved_this_turn_fails(make_passage, retrieved):
    other = make_passage()

    errors = validate_grounding(
        answer("Flat sales [1].", cite(other, "iPhone net sales were relatively flat")), retrieved
    )

    assert any("not returned by a tool" in e for e in errors)


def test_fabricated_quote_fails(passage, retrieved):
    errors = validate_grounding(
        answer("Sales soared [1].", cite(passage, "iPhone net sales soared during 2024")), retrieved
    )

    assert any("does not appear" in e for e in errors)


def test_altered_number_in_quote_fails(passage, retrieved):
    errors = validate_grounding(answer("$201,813 [1].", cite(passage, "iPhone | $ 201,813")), retrieved)

    assert any("does not appear" in e for e in errors)


@pytest.mark.parametrize(
    "quote",
    [
        "IPHONE NET SALES were   relatively flat",  # case and whitespace
        "iPhone  $ 201,183",  # table pipe dropped
        "Services | 96,169 | 13 %",
        "iPhone net sales … flat during 2024",  # ellipsis joining two real pieces
        "iPhone net sales ... compared to 2023",
    ],
)
def test_quote_matching_tolerates_formatting(passage, retrieved, quote):
    assert validate_grounding(answer("Flat [1].", cite(passage, quote)), retrieved) == []


def test_curly_quotes_and_dashes_match_straight_ones(make_passage):
    passage = make_passage(content="Management’s view — “capacity constrained” through 2025.")

    result = answer("Constrained [1].", cite(passage, "Management's view - \"capacity constrained\""))

    assert validate_grounding(result, {passage.chunk_id: passage}) == []


def test_ellipsis_cannot_hide_an_invented_piece(passage, retrieved):
    quote = "iPhone net sales ... grew because of Apple Intelligence"

    assert validate_grounding(answer("[1]", cite(passage, quote)), retrieved)


def test_too_short_quote_fails(passage, retrieved):
    errors = validate_grounding(answer("Sales [1].", cite(passage, "iPhone")), retrieved)

    assert any("too short" in e for e in errors)


def test_marker_without_citation_fails(passage, retrieved):
    result = answer("Flat [1], services up [2].", cite(passage, "iPhone net sales were relatively flat"))

    assert any("[2]" in e and "no citation" in e for e in validate_grounding(result, retrieved))


def test_citation_never_referenced_fails(passage, retrieved):
    result = answer("Flat.", cite(passage, "iPhone net sales were relatively flat"))

    assert any("never referenced" in e for e in validate_grounding(result, retrieved))


def test_duplicate_citation_indexes_fail(passage, retrieved):
    quote = "iPhone net sales were relatively flat"
    result = answer("Flat [1].", cite(passage, quote, 1), cite(passage, quote, 1))

    assert any("must be unique" in e for e in validate_grounding(result, retrieved))


def test_empty_answer_fails(retrieved):
    assert validate_grounding(answer("  ", status="insufficient_evidence"), retrieved)


def test_grouped_markers_are_parsed():
    assert marker_indexes("Up [1, 3] and down [2].") == [1, 3, 2]
    assert marker_indexes("No markers [a] here.") == []


def test_validator_reports_every_violation(retrieved):
    result = answer(
        "[1] [2]",
        Citation(index=1, chunk_id=uuid4(), quote="nothing like the filing"),
    )

    errors = validate_grounding(result, retrieved)

    assert len(errors) == 2  # [2] has no citation; citation 1's chunk wasn't retrieved
