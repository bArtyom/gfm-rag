"""Bounded CPU-only BIRD-Ent Oracle Mapping Gate scorer."""
import argparse
import collections
import hashlib
import json
import math
import re
import resource
import sys
import time
from pathlib import Path

import sqlglot
from sqlglot import exp

MAX_K_COLUMNS = 10
MAX_K_TABLES = 5
K1 = 1.5
B = 0.75
CREATE_TABLE_RE = re.compile(r'^\s*CREATE\s+TABLE\s+[`"\[]?([^`"\]\s(]+)', re.I)
COLUMN_DECL_RE = re.compile(r'^\s*[`"]([^`"]+)[`"]\s+([A-Za-z][A-Za-z0-9_]*(?:\s*\([^)]*\))?)')


def read_json(path):
    with path.open(encoding='utf-8') as stream:
        return json.load(stream)


def tokenize(text):
    text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', str(text))
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
    return re.findall(r'[a-z0-9]+', text.lower())


def bm25_scores(corpus_tokens, query_tokens):
    n = len(corpus_tokens)
    if n == 0:
        return []
    lengths = [len(doc) for doc in corpus_tokens]
    avgdl = sum(lengths) / n if n else 0.0
    doc_freq = collections.Counter()
    term_freqs = []
    for doc in corpus_tokens:
        tf = collections.Counter(doc)
        term_freqs.append(tf)
        doc_freq.update(tf.keys())
    query_terms = set(query_tokens)
    scores = []
    for index, tf in enumerate(term_freqs):
        score = 0.0
        norm = 1.0 - B + B * (lengths[index] / avgdl if avgdl else 0.0)
        for term in query_terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            idf = math.log(1.0 + (n - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            score += idf * (freq * (K1 + 1.0)) / (freq + K1 * norm)
        scores.append(score)
    return scores


def ddl_table_name(ddl):
    match = CREATE_TABLE_RE.search(ddl)
    if match:
        return match.group(1)
    raise ValueError('DDL has no CREATE TABLE name')


def schema_columns(ddl):
    table_name = ddl_table_name(ddl)
    rows = []
    for line in ddl.splitlines():
        match = COLUMN_DECL_RE.match(line)
        if match:
            rows.append((table_name, match.group(1), match.group(2)))
    if not rows:
        raise ValueError('CREATE TABLE has no recognizable column declarations')
    return rows


def mapping_for_reference(col, source_tables, column_map, all_source_tables, select_aliases):
    name = col.name
    qualifier = col.table
    if not name or col.is_star:
        return None, 'not_a_column'
    if not qualifier and name in select_aliases:
        return None, 'select_alias'
    candidates = []
    if qualifier:
        if qualifier in source_tables:
            candidates = [source_tables[qualifier]]
        elif qualifier in column_map:
            candidates = [qualifier]
        elif len(all_source_tables) == 1:
            candidates = list(all_source_tables)
        else:
            candidates = list(all_source_tables)
    else:
        candidates = list(all_source_tables)
    matches = []
    for table in dict.fromkeys(candidates):
        mapped_columns = column_map.get(table, {})
        if name in mapped_columns:
            matches.append((table, mapped_columns[name]))
    matches = list(dict.fromkeys(matches))
    if len(matches) == 1:
        method = 'exact_qualifier' if qualifier and (qualifier in source_tables or qualifier in column_map) else 'unique_source_fallback'
        return matches[0], method
    if len(matches) > 1:
        return None, 'ambiguous_source_column'
    return None, 'unresolved_column'


def rank_items(scores, ids):
    return sorted(range(len(ids)), key=lambda i: (-scores[i], str(ids[i])))


def recall_at_k(ranked_ids, gold_ids, k):
    if not gold_ids:
        return None
    return len(set(ranked_ids[:k]) & set(gold_ids)) / len(set(gold_ids))


def rr_at_k(ranked_ids, gold_ids):
    gold = set(gold_ids)
    if not gold:
        return None
    for rank, item in enumerate(ranked_ids, 1):
        if item in gold:
            return 1.0 / rank
    return 0.0


def main():
    parser = argparse.ArgumentParser(description='Score the bounded BIRD-Ent BizWeave Oracle Mapping gate.')
    parser.add_argument('--dataset-root', type=Path, required=True, help='Path to the BIRD-Ent directory with JSON assets')
    parser.add_argument('--result-root', type=Path, required=True, help='Private run directory containing frozen selection and mapping files')
    parser.add_argument('--output', type=Path, help='New private output JSON path; defaults under result-root')
    parser.add_argument('--expected-mapping-sha256', required=True, help='Frozen blind review file hash from the registered amendment')
    args = parser.parse_args()
    data_root = args.dataset_root
    result_root = args.result_root
    output = args.output or result_root / 'retrieval_scores.private.json'
    started = time.monotonic()
    mapping_path = result_root / 'oracle_mappings.private.json'
    mapping_sha256 = hashlib.sha256(mapping_path.read_bytes()).hexdigest()
    if mapping_sha256 != args.expected_mapping_sha256:
        raise ValueError('Frozen blinded mapping hash does not match the registered amendment')
    tasks = read_json(data_root / 'BIRD-Ent.json')
    assets = read_json(data_root / 'data_assets.json')
    docs = read_json(data_root / 'knowledge_documents.json')
    table_maps = read_json(data_root / 'table_name_mappings.json')
    column_maps = read_json(data_root / 'column_name_mappings.json')
    selected = read_json(result_root / 'selected_scoring_metadata.private.json')
    annotations = read_json(mapping_path)
    task_by_id = {str(row.get('question_id')): row for row in tasks}
    if isinstance(docs, dict):
        doc_by_id = {str(key): value for key, value in docs.items()}
    else:
        doc_by_id = {str(row.get('knowledge_id', row.get('id'))): row for row in docs}

    case_rows = []
    audit = {'sqlglot_version': sqlglot.__version__, 'case_count': len(selected), 'cases': []}
    for item in selected:
        case_ref = item['case_ref']
        task = task_by_id.get(str(item['question_id']))
        if task is None:
            raise ValueError('Selected task missing from pinned task file')
        db = item['eval_db']
        table_map = table_maps[db]
        column_map = column_maps[db]
        ddl_by_id = assets[item['data_asset']]
        physical_to_id = {}
        ddl_by_physical = {}
        for table_id, ddl in ddl_by_id.items():
            physical = ddl_table_name(ddl)
            physical_to_id[physical] = str(table_id)
            ddl_by_physical[physical] = ddl
        db_physical = set(table_map.values())
        missing_physical = sorted(db_physical - set(physical_to_id))
        if missing_physical:
            raise ValueError('Database table mapping missing from selected asset')
        table_candidates = {}
        column_candidates = []
        for physical in sorted(db_physical):
            table_id = physical_to_id[physical]
            table_candidates[table_id] = physical
            for _, column_name, type_text in schema_columns(ddl_by_physical[physical]):
                column_id = table_id + ':' + column_name
                feature_text = physical + ' ' + column_name + ' ' + type_text
                column_candidates.append({
                    'column_id': column_id,
                    'table_id': table_id,
                    'table_name': physical,
                    'column_name': column_name,
                    'tokens': tokenize(feature_text),
                })
        column_candidates.sort(key=lambda row: row['column_id'])
        column_ids = [row['column_id'] for row in column_candidates]
        schema_tokens = [row['tokens'] for row in column_candidates]

        doc_ids = [str(x) for x in task['gold_knowledge_ids']]
        doc_texts = []
        for doc_id in doc_ids:
            doc = doc_by_id.get(doc_id)
            if doc is None:
                raise ValueError('Selected knowledge document missing from pinned file')
            text = doc if isinstance(doc, str) else doc.get('content', doc.get('text', doc.get('document', '')))
            if not isinstance(text, str) or not text:
                raise ValueError('Selected knowledge document has no text')
            doc_texts.append(text)
        question_text = task['question']
        flat_query = tokenize(question_text + ' ' + ' '.join(doc_texts))
        question_tokens = tokenize(question_text)
        flat_scores = bm25_scores(schema_tokens, flat_query)
        schema_only_scores = bm25_scores(schema_tokens, question_tokens)

        graph_claims = []
        all_graph_mapped_columns = set()
        for ann in annotations:
            if ann.get('case_ref') != case_ref or ann.get('status') != 'supported' or not ann.get('graph_edge_eligible'):
                continue
            table_id = str(ann['table_id'])
            target_column_ids = []
            for colname in ann.get('columns', []):
                column_id = table_id + ':' + str(colname)
                if column_id not in set(column_ids):
                    raise ValueError('Frozen mapping targets a column outside the task database schema')
                target_column_ids.append(column_id)
            if target_column_ids:
                all_graph_mapped_columns.update(target_column_ids)
                evidence = ' '.join(str(span.get('text', '')) for span in ann.get('evidence_spans', []))
                claim_text = str(ann.get('claim_summary', '')) + ' ' + evidence
                graph_claims.append({
                    'claim_id': ann['document_ref'] + ':' + str(len(graph_claims)),
                    'column_ids': sorted(set(target_column_ids)),
                    'tokens': tokenize(claim_text),
                })
        claim_scores = bm25_scores([row['tokens'] for row in graph_claims], question_tokens)
        graph_score_by_column = {}
        for claim, score in zip(graph_claims, claim_scores):
            if score > 0.0:
                for column_id in claim['column_ids']:
                    graph_score_by_column[column_id] = max(graph_score_by_column.get(column_id, 0.0), score)
        graph_rank = sorted(
            range(len(column_candidates)),
            key=lambda i: (
                0 if column_ids[i] in graph_score_by_column else 1,
                -graph_score_by_column.get(column_ids[i], schema_only_scores[i]),
                -schema_only_scores[i],
                column_ids[i],
            ),
        )
        flat_rank = rank_items(flat_scores, column_ids)
        flat_ranked_column_ids = [column_ids[i] for i in flat_rank]
        graph_ranked_column_ids = [column_ids[i] for i in graph_rank]

        flat_first_column_rank = {row['table_id']: min(rank for rank, i in enumerate(flat_rank, 1) if column_candidates[i]['table_id'] == row['table_id']) for row in column_candidates}
        graph_first_column_rank = {row['table_id']: min(rank for rank, i in enumerate(graph_rank, 1) if column_candidates[i]['table_id'] == row['table_id']) for row in column_candidates}
        flat_ranked_tables = sorted(table_candidates, key=lambda table_id: (flat_first_column_rank[table_id], table_id))
        graph_ranked_tables = sorted(table_candidates, key=lambda table_id: (graph_first_column_rank[table_id], table_id))

        # The evaluation-only gold SQL is parsed after the blinded mapping file was frozen.
        parse_error = None
        resolved_gold = set()
        unresolved_gold = set()
        resolution_methods = collections.Counter()
        try:
            sql_tree = sqlglot.parse_one(task['original_SQL'], read='sqlite')
            source_tables = {}
            source_table_names = []
            for tbl in sql_tree.find_all(exp.Table):
                old_name = tbl.name
                source_table_names.append(old_name)
                source_tables[tbl.alias_or_name] = old_name
            source_table_names = list(dict.fromkeys(source_table_names))
            select_aliases = {node.alias for node in sql_tree.find_all(exp.Alias) if node.alias}
            for col in sql_tree.find_all(exp.Column):
                if col.is_star:
                    continue
                mapped, method = mapping_for_reference(col, source_tables, column_map, source_table_names, select_aliases)
                if mapped is None:
                    if method != 'select_alias':
                        unresolved_gold.add(((col.table or '').lower(), col.name.lower()))
                    resolution_methods[method] += 1
                    continue
                old_table, ent_column = mapped
                physical = table_map.get(old_table)
                table_id = physical_to_id.get(physical)
                column_id = table_id + ':' + ent_column if table_id is not None else None
                if column_id is None or column_id not in set(column_ids):
                    unresolved_gold.add(((col.table or '').lower(), col.name.lower()))
                    resolution_methods['mapped_target_not_in_schema'] += 1
                else:
                    resolved_gold.add(column_id)
                    resolution_methods[method] += 1
        except Exception as exc:
            parse_error = type(exc).__name__
        gold_denominator = len(resolved_gold) + len(unresolved_gold)
        if parse_error or not resolved_gold:
            flat_recall = graph_recall = flat_rr = graph_rr = None
        else:
            flat_recall = recall_at_k(flat_ranked_column_ids, resolved_gold, MAX_K_COLUMNS)
            graph_recall = recall_at_k(graph_ranked_column_ids, resolved_gold, MAX_K_COLUMNS)
            flat_rr = rr_at_k(flat_ranked_column_ids, resolved_gold)
            graph_rr = rr_at_k(graph_ranked_column_ids, resolved_gold)
        gold_table_ids = set(str(x) for x in task['gold_table_ids'])
        flat_table_recall = recall_at_k(flat_ranked_tables, gold_table_ids, MAX_K_TABLES)
        graph_table_recall = recall_at_k(graph_ranked_tables, gold_table_ids, MAX_K_TABLES)
        case = {
            'case_ref': case_ref,
            'db_table_count': len(table_candidates),
            'schema_column_count': len(column_candidates),
            'linked_document_count': len(doc_texts),
            'document_character_count': sum(map(len, doc_texts)),
            'flat_query_token_count': len(flat_query),
            'question_token_count': len(question_tokens),
            'eligible_graph_claim_count': len(graph_claims),
            'eligible_graph_claim_edges': sum(len(claim['column_ids']) for claim in graph_claims),
            'question_relevant_claim_count': sum(score > 0.0 for score in claim_scores),
            'unique_supported_graph_columns': len(all_graph_mapped_columns),
            'question_relevant_graph_columns': len(graph_score_by_column),
            'sql_parse_error': parse_error,
            'gold_column_resolved_count': len(resolved_gold),
            'gold_column_unresolved_count': len(unresolved_gold),
            'gold_column_denominator': gold_denominator,
            'gold_column_resolution_methods': dict(resolution_methods),
            'flat_column_recall_at_10': flat_recall,
            'oracle_column_recall_at_10': graph_recall,
            'flat_reciprocal_rank': flat_rr,
            'oracle_reciprocal_rank': graph_rr,
            'flat_table_recall_at_5': flat_table_recall,
            'oracle_table_recall_at_5': graph_table_recall,
            'flat_top10_private': flat_ranked_column_ids[:MAX_K_COLUMNS],
            'oracle_top10_private': graph_ranked_column_ids[:MAX_K_COLUMNS],
            'gold_columns_private': sorted(resolved_gold),
            'unresolved_gold_refs_private': sorted([list(x) for x in unresolved_gold]),
            'flat_top5_tables_private': flat_ranked_tables[:MAX_K_TABLES],
            'oracle_top5_tables_private': graph_ranked_tables[:MAX_K_TABLES],
        }
        case_rows.append(case)
        audit['cases'].append({
            'case_ref': case_ref,
            'db_table_count': len(table_candidates),
            'schema_column_count': len(column_candidates),
            'linked_document_count': len(doc_texts),
            'eligible_graph_claim_count': len(graph_claims),
            'eligible_graph_claim_edges': sum(len(claim['column_ids']) for claim in graph_claims),
            'question_relevant_claim_count': sum(score > 0.0 for score in claim_scores),
            'unique_supported_graph_columns': len(all_graph_mapped_columns),
            'question_relevant_graph_columns': len(graph_score_by_column),
            'sql_parse_error': parse_error,
            'gold_column_resolved_count': len(resolved_gold),
            'gold_column_unresolved_count': len(unresolved_gold),
            'gold_column_resolution_methods': dict(resolution_methods),
            'flat_column_recall_at_10': flat_recall,
            'oracle_column_recall_at_10': graph_recall,
            'flat_reciprocal_rank': flat_rr,
            'oracle_reciprocal_rank': graph_rr,
            'flat_table_recall_at_5': flat_table_recall,
            'oracle_table_recall_at_5': graph_table_recall,
        })

    def mean(key):
        values = [case[key] for case in case_rows if case[key] is not None]
        return sum(values) / len(values) if values else None, len(values)
    summary = {
        'run_id': 'bizweave_birdent_oracle_mapping_gate_20261124_001',
        'scoring_run': '002',
        'case_count': len(case_rows),
        'column_metric_case_count': sum(case['flat_column_recall_at_10'] is not None for case in case_rows),
        'unresolved_sql_column_reference_count': sum(case['gold_column_unresolved_count'] for case in case_rows),
        'parsed_gold_column_denominator': sum(case['gold_column_denominator'] for case in case_rows),
        'resolved_gold_column_count': sum(case['gold_column_resolved_count'] for case in case_rows),
        'flat_column_recall_at_10_mean': mean('flat_column_recall_at_10')[0],
        'oracle_column_recall_at_10_mean': mean('oracle_column_recall_at_10')[0],
        'flat_reciprocal_rank_mean': mean('flat_reciprocal_rank')[0],
        'oracle_reciprocal_rank_mean': mean('oracle_reciprocal_rank')[0],
        'flat_table_recall_at_5_mean': mean('flat_table_recall_at_5')[0],
        'oracle_table_recall_at_5_mean': mean('oracle_table_recall_at_5')[0],
        'cases_improved_column_recall': sum(case['oracle_column_recall_at_10'] is not None and case['flat_column_recall_at_10'] is not None and case['oracle_column_recall_at_10'] > case['flat_column_recall_at_10'] for case in case_rows),
        'cases_equal_column_recall': sum(case['oracle_column_recall_at_10'] is not None and case['oracle_column_recall_at_10'] == case['flat_column_recall_at_10'] for case in case_rows),
        'cases_worse_column_recall': sum(case['oracle_column_recall_at_10'] is not None and case['oracle_column_recall_at_10'] < case['flat_column_recall_at_10'] for case in case_rows),
        'sqlglot_version': sqlglot.__version__,
        'mapping_review_sha256': mapping_sha256,
        'wall_time_seconds': round(time.monotonic() - started, 3),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'bm25': {'k1': K1, 'b': B, 'query_term_handling': 'unique terms, no query term frequency multiplier'},
        'candidate_features': 'Enterprise table name + enterprise column name + SQL type; example comments excluded',
        'oracle_rank_order': 'Columns linked to question-relevant claims (BM25 > 0) first by claim BM25, then schema-only BM25; all other columns use schema-only BM25; column ID tie-break',
        'table_rank_order': 'Earliest ranked column per table; table ID tie-break',
        'column_id_format': 'table_id:enterprise_column_name',
        'evaluation_sql_executed': False,
        'model_or_api_calls': 0,
        'gpu_used': False,
        'cases': audit['cases'],
    }
    payload = {'summary': summary, 'case_details_private': case_rows}
    with output.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    print('private_scores:', output)


if __name__ == '__main__':
    main()
