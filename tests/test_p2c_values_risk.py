import pytest

from scripts.text2sql import audit_p2c_values_risk as audit


def test_sql_literals_exclude_limit_patterns_and_constant_only_predicates():
    literals, counts = audit.extract_predicate_literals(
        "SELECT * FROM t WHERE status = 'Active' AND score >= -2 AND name LIKE 'A%' AND 1 = 1 LIMIT 10")
    assert {(item["kind"], item["value"]) for item in literals} == {("string", "active"), ("number", "-2")}
    assert counts["pattern_literals_excluded"] == 1
    assert counts["pagination_literals_excluded"] == 1


def test_literals_inside_functions_are_not_misclassified_as_direct_data_values():
    literals, counts = audit.extract_predicate_literals(
        "SELECT * FROM t WHERE strftime('%Y', day) = '2020' AND status IN ('A', 'B') AND x BETWEEN 1 AND 2")
    assert {item["value"] for item in literals} == {"2020", "a", "b", "1", "2"}
    assert counts["computed_or_function_literals_excluded"] == 1


@pytest.mark.parametrize("literal,text,want", (("1", "10", False), ("1", "1.5", False),
                                              ("active", "inactive", False), ("active", "0 = Active", True),
                                              ("new york", "NEW   YORK", True), ("-2", "-2 = missing", True)))
def test_literal_matching_uses_normalized_boundaries(literal, text, want):
    assert audit.literal_present(literal, audit.normalize(text)) is want


def test_exposure_requires_old_selected_values_and_absence_from_retained_text():
    r0 = {"c": "Column: status; values: A = Active"}
    r1 = {"c": "Column: status"}
    literals = [{"kind": "string", "value": "active"}]
    flags = audit.find_exposures(literals, "show all rows", ["c"], ["c"], r0, r1, {"c"})
    assert len(flags) == 1
    assert flags[0]["input_mentions_literal"] is False
    assert flags[0]["matching_node_retained"] is True
    assert flags[0]["matching_gold_column"] is True
    assert "value" not in flags[0]
    assert audit.find_exposures(literals, "show rows", [], ["c"], r0, r1, {"c"}) == []


def test_other_visible_context_and_user_input_are_handled_separately():
    r0 = {"c": "Column: status; values: Active", "d": "Column: active"}
    r1 = {"c": "Column: status", "d": "Column: active"}
    literals = [{"kind": "string", "value": "active"}]
    assert audit.find_exposures(literals, "rows", ["c"], ["c", "d"], r0, r1, {"c"}) == []
    flags = audit.find_exposures(literals, "active rows", ["c"], ["c"], r0, r1, {"c"})
    assert len(flags) == 1 and flags[0]["input_mentions_literal"] is True


def test_values_also_visible_in_old_nonvalues_text_are_not_exclusive_loss():
    r0 = {"c": "Column: active; values: Active"}
    r1 = {"c": "Column: active"}
    assert audit.find_exposures([{"kind": "string", "value": "active"}], "rows", ["c"], [], r0, r1, {"c"}) == []


@pytest.mark.parametrize("value,text", (("2", "-2"), ("2", "+2"), ("-2", "--2")))
def test_numeric_signs_are_not_ignored(value, text):
    assert not audit.literal_present(value, audit.normalize(text))


def test_parenthesized_and_nested_numeric_negation_preserves_sign():
    literals, _ = audit.extract_predicate_literals("SELECT * FROM t WHERE x > -(2) AND y > -(-3)")
    assert {item["value"] for item in literals} == {"-2", "3"}
