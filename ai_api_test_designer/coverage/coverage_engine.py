"""Coverage & Traceability Engine: design coverage only; does not execute tests."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from collections import defaultdict


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def elements_from_openapi(openapi):
    result = []
    def add(op, eid, kind, description, tokens):
        result.append({"element_id": eid, "element_type": kind,
                       "description": description, "operation_id": op,
                       "match_tokens": tokens})
    for op in openapi.get("operations", []):
        oid = op.get("operation_id") or f'{op.get("method")} {op.get("path")}'
        endpoint = f'{op.get("method","").upper()} {op.get("path","")}'
        add(oid, f"{oid}:operation", "operation", endpoint, [oid])
        for param in op.get("parameters", []):
            name, loc = param.get("name", "unknown"), param.get("in", "parameter")
            fmt = (param.get("schema") or {}).get("format")
            param_tokens = [f"parameter:{name}"]
            if fmt:
                param_tokens.extend([f"format:{name}:{fmt}", f"invalid_format:{name}:{fmt}"])
            add(oid, f"{oid}:parameter:{loc}:{name}", "parameter",
                f"{loc} parameter '{name}'", param_tokens)
            if fmt:
                add(oid, f"{oid}:parameter:{name}:format:{fmt}", "constraint",
                    f"Format {fmt} for parameter '{name}'",
                    [oid, f"format:{name}:{fmt}", f"invalid_format:{name}:{fmt}"])
        body = op.get("request_body") or {}
        for content in body.get("content", []):
            schema = content.get("schema") or {}
            for prop in schema.get("properties", []):
                name = prop.get("name", "unknown")
                add(oid, f"{oid}:request_property:{name}", "request_property",
                    f"Request property '{name}'", [oid, name, f"required_missing:{name}"])
                checks = [
                    ("minimum", prop.get("minimum"), f"below_minimum:{name}"),
                    ("maximum", prop.get("maximum"), f"above_maximum:{name}"),
                    ("max_length", prop.get("max_length"), f"max_length_exceeded:{name}"),
                    ("min_length", prop.get("min_length"), f"min_length:{name}"),
                    ("pattern", prop.get("pattern"), f"pattern_violation:{name}")
                ]
                for label, value, violation in checks:
                    if value is not None:
                        add(oid, f"{oid}:property:{name}:{label}", "constraint",
                            f"{label} constraint for '{name}' ({value})",
                            [oid, f"{label}:{name}", violation])
                enum = prop.get("enum") or []
                if enum:
                    add(oid, f"{oid}:property:{name}:enum", "constraint",
                        f"Allowed values for '{name}': {', '.join(map(str, enum))}",
                        [oid, f"enum:{name}", f"enum_violation:{name}"] +
                        [f"enum:{name}:{v}" for v in enum])
        for response in op.get("responses", []):
            status = str(response.get("status_code", ""))
            if status:
                add(oid, f"{oid}:response:{status}", "response",
                    f"Documented HTTP response {status}", [oid, f"response:{status}"])
        if op.get("security"):
            add(oid, f"{oid}:security", "security",
                "Operation requires authentication/security",
                [oid, "security", "missing_bearer_token"])
    return result


def case_tokens(case):
    return {str(x).strip() for x in ((case.get("source") or {}).get("elements") or [])}


def is_architecture_candidate(case):
    tokens = case_tokens(case)
    return (case.get("category") == "integration_candidate"
            or case.get("test_type") == "integration"
            or "architecture_diagram" in tokens
            or (case.get("source") or {}).get("artifact") == "architecture")


def matches(case, element):
    if case.get("operation_id") != element["operation_id"]:
        return False
    tokens = case_tokens(case)
    if element["element_type"] == "response":
        status = element["element_id"].rsplit(":", 1)[-1]
        expected = case.get("expected_status_code")
        return expected is not None and str(expected) == status
    if element["element_type"] == "operation":
        return element["operation_id"] in tokens
    return any(t in tokens for t in element["match_tokens"] if t != element["operation_id"])


def build_report(openapi, test_data, correlation=None, architecture=None):
    correlation, architecture = correlation or {}, architecture or {}
    cases = test_data.get("test_cases", [])
    confirmed = [c for c in cases if not is_architecture_candidate(c)]
    candidates = [c for c in cases if is_architecture_candidate(c)]
    elements = elements_from_openapi(openapi)
    element_rows = []
    for el in elements:
        yes = [c for c in confirmed if matches(c, el)]
        maybe = [c for c in candidates if matches(c, el)]
        status = "covered" if yes else "candidate_only" if maybe else "uncovered"
        element_rows.append({
            "element_id": el["element_id"], "element_type": el["element_type"],
            "description": el["description"], "operation_id": el["operation_id"],
            "status": status,
            "confirmed_test_case_ids": [c.get("id") for c in yes],
            "candidate_test_case_ids": [c.get("id") for c in maybe]
        })

    mappings = correlation.get("endpoint_service_mappings", [])
    operation_rows = []
    for op in openapi.get("operations", []):
        oid = op.get("operation_id")
        rows = [e for e in element_rows if e["operation_id"] == oid]
        op_cases = [c for c in cases if c.get("operation_id") == oid]
        op_maps = [m for m in mappings if m.get("operation_id") == oid]
        covered = sum(e["status"] == "covered" for e in rows)
        candidate = sum(e["status"] == "candidate_only" for e in rows)
        uncovered = sum(e["status"] == "uncovered" for e in rows)
        operation_rows.append({
            "operation_id": oid,
            "endpoint": f'{op.get("method","").upper()} {op.get("path","")}',
            "total_design_elements": len(rows), "covered_elements": covered,
            "candidate_only_elements": candidate, "uncovered_elements": uncovered,
            "design_coverage_percent": round(100*covered/len(rows), 2) if rows else 0,
            "test_case_ids": [c.get("id") for c in op_cases],
            "architecture_mapping_status": (
                "confirmed" if any(m.get("match_status") == "confirmed" for m in op_maps)
                else "candidate_requires_review" if op_maps else "unmapped"),
            "architecture_mappings": [{
                "candidate_service": m.get("candidate_service"),
                "match_status": m.get("match_status"),
                "score": m.get("score"),
                "requires_review": m.get("requires_review", True)
            } for m in op_maps]
        })

    total = len(element_rows)
    covered = sum(e["status"] == "covered" for e in element_rows)
    candidate = sum(e["status"] == "candidate_only" for e in element_rows)
    uncovered = sum(e["status"] == "uncovered" for e in element_rows)
    case_trace = []
    for c in cases:
        linked = [e["element_id"] for e in elements if matches(c, e)]
        case_trace.append({
            "test_case_id": c.get("id"), "operation_id": c.get("operation_id"),
            "category": c.get("category"),
            "traceability_status": ("architecture_candidate_requires_review"
                                    if is_architecture_candidate(c)
                                    else "linked_to_contract" if linked
                                    else "no_contract_element_match"),
            "contract_element_ids": linked
        })
    unmapped = correlation.get("unmapped_elements") or {}
    return {
        "analysis_type": "coverage_and_traceability",
        "coverage_semantics": "design_coverage_not_execution_coverage",
        "summary": {
            "total_test_cases": len(cases),
            "confirmed_design_test_cases": len(confirmed),
            "architecture_candidate_test_cases": len(candidates),
            "total_contract_design_elements": total,
            "covered_contract_elements": covered,
            "candidate_only_contract_elements": candidate,
            "uncovered_contract_elements": uncovered,
            "design_coverage_percent": round(100*covered/total, 2) if total else 0,
            "operation_count": len(operation_rows),
            "operations_with_at_least_one_test": sum(bool(x["test_case_ids"]) for x in operation_rows)
        },
        "operation_coverage": operation_rows,
        "contract_element_coverage": element_rows,
        "uncovered_elements": [e for e in element_rows if e["status"] == "uncovered"],
        "candidate_only_elements": [e for e in element_rows if e["status"] == "candidate_only"],
        "architecture_traceability": {
            "endpoint_service_mappings": mappings,
            "service_dependencies": correlation.get("service_dependencies", []),
            "confirmed_mapping_count": sum(m.get("match_status") == "confirmed" for m in mappings),
            "candidate_mapping_count": sum(m.get("match_status") == "candidate" for m in mappings),
            "unmapped_services": unmapped.get("services", []),
            "unmapped_architecture_components": unmapped.get("architecture_components", []),
            "review_required": True,
            "note": "Los mapeos heurísticos y las conexiones visuales no son relaciones confirmadas ni aumentan la cobertura funcional."
        },
        "test_case_traceability": case_trace,
        "limitations": [
            "Mide cobertura de diseño; no ejecuta pruebas.",
            "Las relaciones de arquitectura candidatas requieren validación humana.",
            "No infiere reglas de negocio ausentes en los artefactos.",
            "La cobertura se limita a los elementos extraídos del contrato y a la trazabilidad declarada por cada caso."
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Coverage & Traceability Engine")
    parser.add_argument("--openapi", required=True)
    parser.add_argument("--test-cases", required=True)
    parser.add_argument("--correlation", required=True)
    parser.add_argument("--architecture", required=False)
    parser.add_argument("--output", default="coverage_report.json")
    args = parser.parse_args()
    report = build_report(load_json(args.openapi), load_json(args.test_cases),
                          load_json(args.correlation),
                          load_json(args.architecture) if args.architecture else {})
    save_json(report, args.output)
    s = report["summary"]
    print("Coverage & Traceability Engine completed.")
    print(f"Design coverage: {s['design_coverage_percent']}%")
    print(f"Covered: {s['covered_contract_elements']} | Candidate: {s['candidate_only_contract_elements']} | Uncovered: {s['uncovered_contract_elements']}")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
