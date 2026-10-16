from __future__ import annotations

import argparse
import json

from gfmrag_p1_common import prepare_p1_inputs, sha256_text_sequence


EXPECTED_QUERY_TEXT_HASH = (
    "a33e140e6ae5a362b5480a437bc77431b8c878f000e3ea03dadba38108b25634"
)
EXPECTED_SCHEMA_TEXT_HASH = (
    "2089cf5c7d10aa4056c98a19edca44a3fa0bfa17e2c1f0593848f7c935d4f226"
)
EXPECTED_SMOKE_SCHEMA_TEXT_HASH = (
    "580f3eaa6b4fe6783c0cde6c11570aa6fd812036b1143720c5a873ac4ec40806"
)


def matching_variants(variants: dict[str, str], expected: str) -> list[str]:
    return [name for name, value in variants.items() if value == expected]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fallback-encoding", default="cp1252")
    args = parser.parse_args()
    prepared = prepare_p1_inputs(
        load_tokenizer=True, description_fallback_encoding=args.fallback_encoding
    )
    first_db_id = prepared["questions"][0]["db_id"]
    node_orders = {
        "protocol_builder_order": prepared["nodes"],
        "tables_then_columns": sorted(
            prepared["nodes"], key=lambda node: (node.node_type != "table")
        ),
        "node_id_lexicographic": sorted(
            prepared["nodes"], key=lambda node: node.node_id
        ),
        "db_then_type_then_id": sorted(
            prepared["nodes"],
            key=lambda node: (node.db_id, node.node_type, node.node_id),
        ),
        "per_db_tables_then_columns": [
            node
            for db_nodes in prepared["nodes_by_db"].values()
            for node in (
                [candidate for candidate in db_nodes if candidate.node_type == "table"]
                + [candidate for candidate in db_nodes if candidate.node_type == "column"]
            )
        ],
    }
    schema_order_hashes = {
        order: sha256_text_sequence([node.text for node in nodes])["newline_join"]
        for order, nodes in node_orders.items()
    }
    smoke_node_orders = {
        order: [node for node in nodes if node.db_id == first_db_id]
        for order, nodes in node_orders.items()
    }
    smoke_schema_order_hashes = {
        order: sha256_text_sequence([node.text for node in nodes])["newline_join"]
        for order, nodes in smoke_node_orders.items()
    }
    actual = {
        "questions": len(prepared["questions"]),
        "schema_nodes": len(prepared["nodes"]),
        "table_nodes": sum(node.node_type == "table" for node in prepared["nodes"]),
        "column_nodes": sum(node.node_type == "column" for node in prepared["nodes"]),
        "label_counts": prepared["label_counts"],
        "frozen_hashes": prepared["frozen_hashes"],
        "text_hashes": prepared["text_hashes"],
        "old_text_hash_matches": {
            "query_prompts": matching_variants(
                prepared["text_hashes"]["query_prompts"], EXPECTED_QUERY_TEXT_HASH
            ),
            "schema_nodes": matching_variants(
                prepared["text_hashes"]["schema_nodes"], EXPECTED_SCHEMA_TEXT_HASH
            ),
        },
        "schema_hash_order_probe": {
            "full_run_expected": EXPECTED_SCHEMA_TEXT_HASH,
            "full_run_newline_join_hashes": schema_order_hashes,
            "full_run_matching_order": [
                order
                for order, value in schema_order_hashes.items()
                if value == EXPECTED_SCHEMA_TEXT_HASH
            ],
            "five_question_expected": EXPECTED_SMOKE_SCHEMA_TEXT_HASH,
            "first_db_newline_join_hashes": smoke_schema_order_hashes,
            "first_db_matching_order": [
                order
                for order, value in smoke_schema_order_hashes.items()
                if value == EXPECTED_SMOKE_SCHEMA_TEXT_HASH
            ],
        },
        "token_stats": prepared["token_stats"],
    }
    print(json.dumps(actual, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
