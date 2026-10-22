from scripts.text2sql import p2d_inputs as p


def test_e0_e2_nodes_are_identical_and_only_values_text_changes():
    row = {'arms': {arm: {'budgets': {'1024': {'selected_ids': nodes}}} for arm, nodes in [('V00', ['a']), ('V01', ['a', 'b'])]}}
    out = p.contexts(row, {'a': 'Column t.a; values: secret', 'b': 'Column t.b'}, {'a': 'Column t.a', 'b': 'Column t.b'})
    assert out['E0']['node_ids'] == out['E2']['node_ids'] == ['a']
    assert out['E2']['text'] == 'Column t.a'
    assert out['E1']['text'] == 'Column t.a\nColumn t.b'


def test_messages_use_only_question_evidence_context_and_fixed_template():
    for context in ['old', 'new']:
        msg = p.messages('Q', 'E', context)
        assert msg[0]['content'] == p.SYSTEM
        assert msg[1]['content'].replace(context, '<CTX>') == 'Database schema context:\n<CTX>\n\nQuestion: Q\nEvidence: E\n\nSQL:'


def test_matching_is_exact_without_replacement_and_records_gaps():
    features = {0: ('db', ('eq',), 1, 2, True), 1: ('db', ('eq',), 1, 2, True),
                2: ('db', ('eq',), 1, 2, True), 3: ('db', ('eq',), 1, 3, True)}
    pairs, gaps = p.match_controls([0, 1, 3], features, 20261021)
    assert len(pairs) == 1 and pairs[0][1] == 2
    assert set(gaps) == {1, 3}
    assert p.match_controls([0, 1, 3], features, 20261021) == (pairs, gaps)
