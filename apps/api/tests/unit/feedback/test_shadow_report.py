"""Shadow report arithmetic and the parsing of stored shadow answers (FR-81)."""

from app.feedback.shadow_report import (
    ShadowSample,
    format_table,
    samples_for,
    summarize,
)


def sample(human: str, shadow: str | None, confidence: float | None) -> ShadowSample:
    return ShadowSample(
        question="keep", human_choice=human, shadow_choice=shadow, shadow_confidence=confidence
    )


def test_cutoff_counts_decided_agreed_and_wrong() -> None:
    samples = [
        sample("A", "A", 0.95),  # decided and right at every cutoff up to 0.9
        sample("B", "A", 0.75),  # decided and wrong from cutoff 0.5 to 0.7
        sample("A", "A", 0.55),  # decided only at 0.5
        sample("A", None, None),  # Laya gave nothing: always skipped
    ]

    rows = {row.cutoff: row for row in summarize(samples, cutoffs=(0.5, 0.7, 0.9))}

    assert (rows[0.5].labelled, rows[0.5].decided, rows[0.5].agreed, rows[0.5].wrong) == (
        4,
        3,
        2,
        1,
    )
    assert (rows[0.7].decided, rows[0.7].wrong) == (2, 1)
    assert (rows[0.9].decided, rows[0.9].wrong, rows[0.9].skipped) == (1, 0, 3)


def test_empty_sample_set_reports_zeroes_not_errors() -> None:
    rows = summarize([])

    assert all(row.labelled == 0 and row.decided == 0 for row in rows)


def test_samples_pair_each_human_label_with_the_shadow_answer() -> None:
    gold = {"keep": {"B": 1.0}, "topic": {"ai": 1.0}}
    triage = {
        "shadow": {
            "answers": {
                "keep": {"type": "choice", "choice": "B", "confidence": 0.9, "source": "laya"},
                # no shadow answer for "topic": that question is not paired
            }
        }
    }

    (only,) = samples_for(gold, triage)

    assert only == ShadowSample("keep", "B", "B", 0.9)


def test_malformed_shadow_entries_are_ignored_not_fatal() -> None:
    gold = {"keep": {"A": 1.0}}
    triage = {"shadow": {"answers": {"keep": {"confidence": "very high"}}}}

    assert samples_for(gold, triage) == []  # invalid answer is not a shadow opinion


def test_missing_or_non_mapping_stored_values_yield_no_samples() -> None:
    assert samples_for(None, None) == []
    assert samples_for({"keep": "A"}, {"shadow": "nope"}) == []


def test_table_has_one_line_per_cutoff_and_a_header() -> None:
    rows = summarize([sample("A", "A", 0.9)], cutoffs=(0.5, 0.9))

    table = format_table("news_radar", 14, rows).splitlines()

    assert table[0] == "shadow report: niche=news_radar last 14 days"
    assert len(table) == 2 + 2  # title, column header, two cutoffs
