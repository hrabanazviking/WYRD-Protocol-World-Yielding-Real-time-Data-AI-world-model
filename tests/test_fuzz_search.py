"""Fuzz corpus 3/3 — hostile FTS5 search strings (Track 1, P1).

Corpus-first: written against the unpatched tree, where the hostile
cases go red (``sqlite3.OperationalError`` from the ``"``-breakout,
FTS5 operators interpreted instead of matched literally). After the
phrase-escape lands, every case runs with 0 unhandled exceptions and
operator-like input matches literally.

Boundary under test: ``PersistentMemoryStore.search``.
"""
from __future__ import annotations


import pytest

from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.demo_seed import build_seed_fact


def _seeded_store(db_path) -> PersistentMemoryStore:
    store = PersistentMemoryStore(str(db_path))
    seeds = [
        ("r1", "the quick brown fox", "jumps over the lazy dog"),
        ("r2", "fish or fowl", "a question of dinner"),
        ("r3", 'say "hi" there', "a quoted greeting"),
        ("r4", "bread and butter", "simple fare"),
        ("r5", "not today", "a refusal"),
        ("r6", "near the fire", "where the stories are told"),
    ]
    for rid, title, summary in seeds:
        rec = build_seed_fact(record_id=rid)
        rec.content.title = title
        rec.content.summary = summary
        store.add(rec)
    return store


def _ids(results) -> set[str]:
    return {r.record_id for r in results}


@pytest.fixture()
def store(tmp_path):
    return _seeded_store(tmp_path / "search.db")


# ---------------------------------------------------------------------------
# Must-accept: valid-path equivalence (the good query never notices the guard)
# ---------------------------------------------------------------------------

class TestSearchAccepts:
    def test_plain_term_finds_record(self, store):
        assert "r1" in _ids(store.search("quick"))

    def test_multi_term_finds_record(self, store):
        assert "r1" in _ids(store.search("quick fox"))

    def test_case_insensitive(self, store):
        assert "r1" in _ids(store.search("QUICK"))

    def test_empty_query_returns_empty(self, store):
        assert store.search("") == []

    def test_whitespace_only_returns_empty(self, store):
        assert store.search("   \t\n  ") == []

    def test_query_at_char_boundary_accepted(self, store):
        assert isinstance(store.search("x" * 10_000), list)

    def test_100_terms_accepted(self, store):
        assert isinstance(store.search(" ".join(f"w{i}" for i in range(100))), list)

    def test_unicode_query_no_crash(self, store):
        assert isinstance(store.search("ᚠᚢᚦᚨᚱ"), list)

    def test_newlines_and_tabs_no_crash(self, store):
        assert isinstance(store.search("quick\n\tfox"), list)


# ---------------------------------------------------------------------------
# Must-never: OperationalError from any input; operators match literally
# ---------------------------------------------------------------------------

class TestSearchHostile:
    def test_quote_breakout_no_crash_no_match(self, store):
        # The injection: a '"' inside a term must not break its phrase.
        # No record contains the literal quick"brow, so: no crash, no rows.
        assert store.search('quick"brow') == []

    def test_quoted_phrase_matches_literally(self, store):
        # The '"' is escaped to '""' — the phrase stays one phrase and
        # matches the record that literally contains "hi".
        assert "r3" in _ids(store.search('"hi"'))

    def test_lone_quote_no_crash(self, store):
        assert isinstance(store.search('"'), list)

    def test_double_quote_no_crash(self, store):
        assert isinstance(store.search('""'), list)

    def test_unbalanced_quotes_no_crash(self, store):
        assert isinstance(store.search('say "hi'), list)

    def test_trailing_quote_no_crash(self, store):
        assert isinstance(store.search('a"b"c'), list)

    def test_or_matches_literally(self, store):
        # "OR" must match the word "or" (r2), not act as an operator.
        assert "r2" in _ids(store.search("OR"))

    def test_and_matches_literally(self, store):
        assert "r4" in _ids(store.search("AND"))

    def test_not_matches_literally(self, store):
        assert "r5" in _ids(store.search("NOT"))

    def test_near_matches_literally(self, store):
        assert "r6" in _ids(store.search("NEAR"))

    def test_near_paren_no_crash(self, store):
        assert isinstance(store.search("NEAR("), list)

    def test_star_no_crash(self, store):
        assert isinstance(store.search("*"), list)

    def test_caret_no_crash(self, store):
        assert isinstance(store.search("^"), list)

    def test_column_prefix_no_crash(self, store):
        assert isinstance(store.search("title:fox"), list)

    def test_parens_no_crash(self, store):
        assert isinstance(store.search("(quick)"), list)

    def test_sql_metacharacters_no_crash(self, store):
        assert isinstance(store.search("' OR '1'='1"), list)

    def test_drop_table_no_crash_table_intact(self, store):
        assert isinstance(store.search('"; DROP TABLE memory_records; --'), list)
        # The table survived: valid search still works.
        assert "r1" in _ids(store.search("quick"))

    def test_long_single_term_no_crash(self, store):
        assert isinstance(store.search("z" * 5000), list)

    def test_mixed_hostile_soup_no_crash(self, store):
        soup = '" OR * NEAR( title: ^ "unbalanced'
        assert isinstance(store.search(soup), list)


@pytest.mark.parametrize("op", [
    "OR", "AND", "NOT", "NEAR", "*", "^", "(", ")", ":", "-", "+", "~",
    "OR 1=1", "title:", '"', '""', "a\"b",
])
def test_operator_soup_never_raises(store, op):
    assert isinstance(store.search(op), list)


@pytest.mark.parametrize("op", ["OR", "AND", "NOT"])
def test_bare_operators_alone_no_crash(store, op):
    # Even with no other terms: the phrase builder must not produce
    # a bare-operator MATCH expression.
    assert isinstance(store.search(op), list)


# ---------------------------------------------------------------------------
# Must-reject: the caps (named field, never silent truncation)
# ---------------------------------------------------------------------------

class TestSearchCaps:
    def test_query_over_10k_chars_rejected_naming_field(self, store):
        with pytest.raises(ValueError, match="query"):
            store.search("x" * 10_001)

    def test_over_100_terms_rejected_naming_field(self, store):
        with pytest.raises(ValueError, match="query"):
            store.search(" ".join(f"w{i}" for i in range(101)))


# ---------------------------------------------------------------------------
# Search boundary edges: exact caps and literal-operator matching
# ---------------------------------------------------------------------------

class TestSearchBoundaryEdges:
    def test_query_at_10k_chars_accepted(self, store):
        assert store.search("x" * 10_000) == []

    def test_exactly_100_terms_accepted(self, store):
        assert store.search(" ".join(f"w{i}" for i in range(100))) == []

    def test_blank_whitespace_query_returns_empty(self, store):
        assert store.search("   \t\n  ") == []

    def test_none_query_rejected_naming_field(self, store):
        with pytest.raises(ValueError, match="query"):
            store.search(None)

    def test_non_string_query_rejected_naming_field(self, store):
        with pytest.raises(ValueError, match="query"):
            store.search(123)

    def test_newline_splits_terms_literally(self, store):
        # "quick\nfox" is two literal terms, not a syntax trick
        assert _ids(store.search("quick\nfox")) == {"r1"}

    def test_fullwidth_operator_no_crash(self, store):
        assert isinstance(store.search("ＯＲ"), list)

    def test_hostile_term_among_100_terms_no_crash(self, store):
        # The hostile term splits into 3 whitespace terms; 97 + 3 = 100
        terms = ["w%d" % i for i in range(97)] + ['" OR "1"="1']
        assert isinstance(store.search(" ".join(terms)), list)

    def test_limit_parameter_honored(self, store):
        results = store.search("the", limit=1)
        assert len(results) == 1

    def test_quoted_seed_matches_literally(self, store):
        # r3's title contains literal quotes; searching the quoted
        # word finds it instead of breaking FTS syntax
        assert "r3" in _ids(store.search('"hi"'))
