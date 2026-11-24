"""Validate private Codex annotations against the frozen review packet."""
import argparse
import json
from collections import Counter
from pathlib import Path

ALLOWED_STATUSES = {
    "direct_supported",
    "inferred",
    "ambiguous",
    "conflict",
    "proposed_schema",
    "unsupported",
}
FORBIDDEN_PACKET_KEYS = {
    "question",
    "question_text",
    "original_sql",
    "gold_sql",
    "gold_table_ids",
    "gold_column_ids",
    "question_id",
}


def read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def reject_forbidden_keys(value):
    if isinstance(value, dict):
        forbidden = FORBIDDEN_PACKET_KEYS & set(value)
        if forbidden:
            raise ValueError("Review packet contains a forbidden label/question field")
        for child in value.values():
            reject_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            reject_forbidden_keys(child)


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = read_jsonl(args.packet)
    annotations = read_jsonl(args.annotations)
    for row in packet:
        reject_forbidden_keys(row)
    packet_by_case = {row["case_id"]: row for row in packet}
    annotation_by_case = {row["case_id"]: row for row in annotations}
    if len(packet_by_case) != 30 or len(annotation_by_case) != 30 or set(packet_by_case) != set(annotation_by_case):
        raise ValueError("Packet and annotation case IDs must match the 30 preregistered cases exactly")

    validated = []
    status_counts = Counter()
    edge_count = 0
    dependency_cases = set()
    exact_span_count = 0
    for case_id in sorted(packet_by_case):
        case = packet_by_case[case_id]
        annotation = annotation_by_case[case_id]
        doc = case["document"]
        schema = {
            table["name"]: {column["name"] for column in table["columns"]}
            for table in case["schema"]
        }
        output_assertions = []
        for assertion in annotation.get("assertions", []):
            status = assertion.get("status")
            if status not in ALLOWED_STATUSES:
                raise ValueError("Annotation uses an unregistered review status")
            status_counts[status] += 1
            evidence = assertion.get("evidence_span")
            evidence_text = evidence.get("text") if isinstance(evidence, dict) else evidence
            mappings = assertion.get("mappings", [])
            validated_mappings = []
            if status == "direct_supported":
                if not isinstance(evidence_text, str) or not evidence_text.strip():
                    raise ValueError("Direct-supported assertion is missing an exact source span")
                start = doc.find(evidence_text)
                if start < 0:
                    raise ValueError("Direct-supported evidence span is not an exact document substring")
                end = start + len(evidence_text)
                exact_span_count += 1
                if not mappings:
                    raise ValueError("Direct-supported assertion has no schema target")
                for mapping in mappings:
                    table_name = mapping.get("table")
                    column_name = mapping.get("column")
                    if table_name not in schema or column_name not in schema[table_name]:
                        raise ValueError("Direct-supported mapping target is absent from the paired schema")
                    validated_mappings.append({"table": table_name, "column": column_name})
                    edge_count += 1
                if assertion.get("multi_column_dependency"):
                    if len({(row["table"], row["column"]) for row in validated_mappings}) < 2:
                        raise ValueError("Multi-column dependency must target at least two distinct columns")
                    dependency_cases.add(case_id)
                assertion_out = dict(assertion)
                assertion_out["evidence_span"] = {"text": evidence_text, "start": start, "end": end}
                assertion_out["mappings"] = validated_mappings
                output_assertions.append(assertion_out)
            else:
                output_assertions.append(assertion)
        validated.append({"case_id": case_id, "assertions": output_assertions})

    write_json(args.output, {"cases": validated})
    print(json.dumps({
        "cases_validated": len(validated),
        "assertions_by_status": dict(sorted(status_counts.items())),
        "direct_supported_edges": edge_count,
        "direct_supported_assertions_with_exact_spans": exact_span_count,
        "multi_column_dependency_cases": len(dependency_cases),
        "exact_span_rate": 1.0 if exact_span_count == sum(1 for row in validated for assertion in row["assertions"] if assertion["status"] == "direct_supported") else 0.0,
        "schema_membership_validation_rate": 1.0,
        "validated_output": str(args.output),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
