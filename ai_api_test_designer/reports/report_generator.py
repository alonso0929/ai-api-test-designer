"""Report Generator for AI API Test Designer.

Consolida los artefactos generados por los analizadores y motores anteriores.
No ejecuta pruebas ni convierte inferencias arquitectónicas en hechos confirmados.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"El archivo debe contener un objeto JSON: {path}")
    return data


def save_json(data: dict[str, Any], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def save_text(content: str, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _count_by(items: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        label = str(item.get(key) or "unspecified")
        counts[label] = counts.get(label, 0) + 1
    return counts


def build_consolidated_report(
    openapi: dict,
    architecture: dict,
    correlation: dict,
    test_data: dict,
    coverage: dict,
) -> dict:
    operations = _list(openapi.get("operations"))
    components = _list(architecture.get("components"))
    connections = _list(architecture.get("connections"))
    mappings = _list(correlation.get("endpoint_service_mappings"))
    dependencies = _list(correlation.get("service_dependencies"))
    cases = _list(test_data.get("test_cases"))
    operation_coverage = _list(coverage.get("operation_coverage"))
    element_coverage = _list(coverage.get("contract_element_coverage"))
    traceability = _list(coverage.get("test_case_traceability"))

    case_by_id = {str(case.get("id")): case for case in cases if case.get("id")}
    trace_by_id = {str(row.get("test_case_id")): row for row in traceability}

    test_case_rows = []
    for case in cases:
        trace = trace_by_id.get(str(case.get("id")), {})
        test_case_rows.append({
            "id": case.get("id"),
            "title": case.get("title"),
            "operation_id": case.get("operation_id"),
            "endpoint": case.get("endpoint"),
            "category": case.get("category"),
            "test_type": case.get("test_type"),
            "priority": case.get("priority"),
            "expected_status_code": case.get("expected_status_code"),
            "traceability_status": trace.get("traceability_status", "not_evaluated"),
            "contract_element_ids": trace.get("contract_element_ids", []),
            "requires_architecture_review": (
                trace.get("traceability_status") == "architecture_candidate_requires_review"
            ),
        })

    uncovered = _list(coverage.get("uncovered_elements"))
    candidate_only = _list(coverage.get("candidate_only_elements"))
    architecture_trace = coverage.get("architecture_traceability") or {}
    coverage_summary = coverage.get("summary") or {}
    test_summary = test_data.get("summary") or {}
    correlation_summary = correlation.get("summary") or {}
    openapi_summary = openapi.get("inventory") or {}

    review_items = []
    for mapping in mappings:
        if mapping.get("match_status") != "confirmed" or mapping.get("requires_review"):
            review_items.append({
                "type": "endpoint_service_mapping",
                "subject": mapping.get("endpoint"),
                "candidate": mapping.get("candidate_service"),
                "status": mapping.get("match_status"),
                "reason": "La asociación se basa en similitud heurística y requiere validación.",
            })
    for dependency in dependencies:
        if dependency.get("requires_review", True):
            review_items.append({
                "type": "service_dependency",
                "subject": dependency.get("service"),
                "candidate": dependency.get("dependency"),
                "status": "requires_review",
                "reason": "La conexión visual no confirma semántica de lectura o escritura.",
            })
    for element in uncovered:
        review_items.append({
            "type": "uncovered_contract_element",
            "subject": element.get("element_id"),
            "candidate": None,
            "status": "uncovered",
            "reason": element.get("description"),
        })

    report = {
        "analysis_type": "consolidated_test_design_report",
        "report_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "report_semantics": "design_analysis_not_test_execution",
        "contract": {
            "title": (openapi.get("contract") or {}).get("title"),
            "version": (openapi.get("contract") or {}).get("version"),
            "openapi_version": (openapi.get("contract") or {}).get("openapi_version"),
            "validation": openapi.get("validation") or {},
            "inventory": openapi_summary,
            "operations": [
                {
                    "operation_id": op.get("operation_id"),
                    "method": str(op.get("method") or "").upper(),
                    "path": op.get("path"),
                    "summary": op.get("summary"),
                    "deprecated": op.get("deprecated", False),
                }
                for op in operations
            ],
        },
        "architecture": {
            "analysis_type": architecture.get("analysis_type"),
            "model": architecture.get("model"),
            "summary": architecture.get("summary"),
            "component_count": len(components),
            "connection_count": len(connections),
            "components": components,
            "connections": connections,
            "ambiguities": _list(architecture.get("ambiguities")),
            "warnings": _list(architecture.get("warnings")),
            "quality_note": architecture.get("quality_note"),
        },
        "correlation": {
            "summary": correlation_summary,
            "endpoint_service_mappings": mappings,
            "service_dependencies": dependencies,
            "unmapped_elements": correlation.get("unmapped_elements") or {},
            "ambiguities": _list(correlation.get("ambiguities")),
            "warnings": _list(correlation.get("warnings")),
            "quality_note": correlation.get("quality_note"),
        },
        "test_design": {
            "summary": test_summary,
            "category_counts": _count_by(cases, "category"),
            "test_type_counts": _count_by(cases, "test_type"),
            "test_cases": test_case_rows,
            "assumptions": _list(test_data.get("assumptions")),
            "limitations": _list(test_data.get("limitations")),
        },
        "coverage_and_traceability": {
            "semantics": coverage.get("coverage_semantics"),
            "summary": coverage_summary,
            "operation_coverage": operation_coverage,
            "contract_element_coverage": element_coverage,
            "uncovered_elements": uncovered,
            "candidate_only_elements": candidate_only,
            "test_case_traceability": traceability,
            "architecture_traceability": architecture_trace,
            "limitations": _list(coverage.get("limitations")),
        },
        "review_required": review_items,
        "conclusions": [
            f"Se analizaron {len(operations)} operaciones del contrato.",
            f"Se consolidaron {len(cases)} casos de prueba diseñados.",
            (
                f"La cobertura de diseño del contrato es "
                f"{coverage_summary.get('design_coverage_percent', 0)}%; "
                "este valor no representa ejecución de pruebas."
            ),
            (
                f"Se identificaron {len(review_items)} elementos que requieren "
                "revisión o atención antes de considerar cerrado el diseño."
            ),
        ],
        "global_limitations": [
            "El informe consolida resultados de análisis y diseño; no ejecuta pruebas.",
            "Los mapeos entre endpoints y servicios son candidatos hasta su validación.",
            "Las relaciones entre servicios y bases de datos no prueban operaciones de lectura o escritura.",
            "No se infieren reglas de negocio que no estén presentes en los artefactos de entrada.",
            "La cobertura depende de los elementos extraídos y de la trazabilidad declarada por los casos.",
        ],
        "input_artifacts": {
            "openapi": "openapi_analysis.json",
            "architecture": "architecture_analysis.json",
            "correlation": "correlation_analysis.json",
            "test_cases": "test_cases.json",
            "coverage": "coverage_report.json",
        },
    }
    return report


def render_markdown(report: dict) -> str:
    contract = report.get("contract") or {}
    coverage = report.get("coverage_and_traceability") or {}
    cov_summary = coverage.get("summary") or {}
    test_design = report.get("test_design") or {}
    test_summary = test_design.get("summary") or {}
    correlation = report.get("correlation") or {}
    corr_summary = correlation.get("summary") or {}
    architecture = report.get("architecture") or {}

    lines = [
        f"# Informe consolidado de diseño de pruebas",
        "",
        f"**Contrato:** {contract.get('title') or 'No especificado'} "
        f"**Versión:** {contract.get('version') or 'No especificada'}",
        f"**Generado (UTC):** {report.get('generated_at_utc')}",
        "",
        "> Este informe representa análisis y cobertura de diseño. No implica que los casos hayan sido ejecutados.",
        "",
        "## 1. Resumen ejecutivo",
        "",
        f"- Operaciones OpenAPI: **{len(contract.get('operations') or [])}**",
        f"- Casos de prueba diseñados: **{test_summary.get('total_test_cases', 0)}**",
        f"- Cobertura de diseño: **{cov_summary.get('design_coverage_percent', 0)}%**",
        f"- Elementos del contrato cubiertos: **{cov_summary.get('covered_contract_elements', 0)} / {cov_summary.get('total_contract_design_elements', 0)}**",
        f"- Elementos sin cobertura: **{cov_summary.get('uncovered_contract_elements', 0)}**",
        f"- Casos de integración candidatos: **{test_summary.get('integration_candidate_cases', cov_summary.get('architecture_candidate_test_cases', 0))}**",
        "",
        "## 2. Contrato OpenAPI",
        "",
        f"- Título: {contract.get('title')}",
        f"- Versión OpenAPI: {contract.get('openapi_version')}",
        f"- Validación: {'válido' if (contract.get('validation') or {}).get('valid') else 'no confirmada'}",
        "",
        "| Operación | Método | Ruta | Obsoleta |",
        "|---|---:|---|---|",
    ]
    for op in contract.get("operations") or []:
        lines.append(
            f"| {op.get('operation_id')} | {op.get('method')} | `{op.get('path')}` | "
            f"{'Sí' if op.get('deprecated') else 'No'} |"
        )

    lines += [
        "",
        "## 3. Diseño de casos de prueba",
        "",
        f"- Casos positivos: {test_summary.get('positive_cases', 0)}",
        f"- Casos negativos: {test_summary.get('negative_cases', 0)}",
        f"- Casos de seguridad: {test_summary.get('security_cases', 0)}",
        f"- Casos candidatos de integración: {test_summary.get('integration_candidate_cases', 0)}",
        "",
        "| ID | Operación | Categoría | Prioridad | HTTP esperado | Trazabilidad |",
        "|---|---|---|---|---:|---|",
    ]
    for case in test_design.get("test_cases") or []:
        lines.append(
            f"| {case.get('id')} | {case.get('operation_id')} | {case.get('category')} | "
            f"{case.get('priority')} | {case.get('expected_status_code') if case.get('expected_status_code') is not None else 'No definido'} | "
            f"{case.get('traceability_status')} |"
        )

    lines += [
        "",
        "## 4. Cobertura por operación",
        "",
        "| Operación | Elementos | Cubiertos | Solo candidatos | Sin cobertura | Cobertura | Mapeo arquitectónico |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for op in coverage.get("operation_coverage") or []:
        lines.append(
            f"| {op.get('operation_id')} | {op.get('total_design_elements')} | "
            f"{op.get('covered_elements')} | {op.get('candidate_only_elements')} | "
            f"{op.get('uncovered_elements')} | {op.get('design_coverage_percent')}% | "
            f"{op.get('architecture_mapping_status')} |"
        )

    lines += ["", "### Elementos sin cobertura", ""]
    uncovered = coverage.get("uncovered_elements") or []
    if uncovered:
        for element in uncovered:
            lines.append(f"- **{element.get('element_id')}**: {element.get('description')}")
    else:
        lines.append("No se identificaron elementos sin cobertura.")

    lines += [
        "",
        "## 5. Correlación con arquitectura",
        "",
        f"- Componentes detectados: {architecture.get('component_count', 0)}",
        f"- Conexiones detectadas: {architecture.get('connection_count', 0)}",
        f"- Mapeos confirmados: {corr_summary.get('confirmed_mappings', 0)}",
        f"- Mapeos candidatos: {corr_summary.get('candidate_mappings', 0)}",
        "",
        "| Endpoint | Servicio candidato | Estado | Revisión requerida |",
        "|---|---|---|---|",
    ]
    for mapping in correlation.get("endpoint_service_mappings") or []:
        lines.append(
            f"| {mapping.get('endpoint')} | {mapping.get('candidate_service')} | "
            f"{mapping.get('match_status')} | {'Sí' if mapping.get('requires_review') else 'No'} |"
        )

    unmapped = correlation.get("unmapped_elements") or {}
    lines += [
        "",
        f"- Servicios sin mapeo: {', '.join(unmapped.get('services') or []) or 'Ninguno'}",
        f"- Componentes arquitectónicos sin mapeo: {', '.join(unmapped.get('architecture_components') or []) or 'Ninguno'}",
        "",
        "## 6. Puntos que requieren revisión",
        "",
    ]
    review_items = report.get("review_required") or []
    if review_items:
        for item in review_items:
            lines.append(
                f"- **{item.get('type')} — {item.get('subject')}**: "
                f"{item.get('reason')}"
            )
    else:
        lines.append("No se identificaron puntos pendientes de revisión.")

    lines += ["", "## 7. Supuestos y limitaciones", ""]
    for item in test_design.get("assumptions") or []:
        lines.append(f"- Supuesto: {item}")
    for item in report.get("global_limitations") or []:
        lines.append(f"- {item}")

    lines += ["", "## 8. Conclusiones", ""]
    for item in report.get("conclusions") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolida el informe de diseño de pruebas.")
    parser.add_argument("--openapi", required=True, help="Resultado de OpenAPI Analyzer.")
    parser.add_argument("--architecture", required=True, help="Resultado de Architecture Vision Analyzer.")
    parser.add_argument("--correlation", required=True, help="Resultado de Contract-Architecture Correlator.")
    parser.add_argument("--test-cases", required=True, help="Resultado de Test Case Generator.")
    parser.add_argument("--coverage", required=True, help="Resultado de Coverage & Traceability Engine.")
    parser.add_argument("--output", default="test_design_report.json", help="Ruta del informe JSON.")
    parser.add_argument("--markdown", default="test_design_report.md", help="Ruta del informe Markdown.")
    args = parser.parse_args()

    report = build_consolidated_report(
        load_json(args.openapi),
        load_json(args.architecture),
        load_json(args.correlation),
        load_json(args.test_cases),
        load_json(args.coverage),
    )
    save_json(report, args.output)
    save_text(render_markdown(report), args.markdown)

    summary = report["coverage_and_traceability"]["summary"]
    print("Report Generator completed.")
    print(f"Operations: {len(report['contract']['operations'])}")
    print(f"Test cases: {report['test_design']['summary'].get('total_test_cases', 0)}")
    print(f"Design coverage: {summary.get('design_coverage_percent', 0)}%")
    print(f"JSON report: {args.output}")
    print(f"Markdown report: {args.markdown}")


if __name__ == "__main__":
    main()
