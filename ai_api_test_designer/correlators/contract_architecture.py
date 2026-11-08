import argparse
import json
from pathlib import Path

from .matching_engine import match_operation_to_services


class CorrelationError(Exception):
    pass


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


def _operations(document):
    operations = [
        item for item in _list(document.get("operations"))
        if isinstance(item, dict)
    ]

    if operations:
        return operations

    found = []

    for path, path_item in _dict(document.get("paths")).items():
        for method, operation in _dict(path_item).items():
            if method.lower() not in {
                "get", "post", "put", "patch", "delete",
                "options", "head", "trace"
            }:
                continue

            operation = _dict(operation)

            found.append({
                **operation,
                "path": path,
                "method": method.lower(),
                "operation_id": operation.get("operationId"),
                "tags": operation.get("tags") or [],
            })

    return found


def _component_type(component):
    return str(component.get("type") or "unknown").lower()


def correlate(openapi, architecture):
    if not isinstance(openapi, dict) or not isinstance(architecture, dict):
        raise CorrelationError(
            "Both inputs must be JSON objects."
        )

    operations = _operations(openapi)

    components = [
        item for item in _list(architecture.get("components"))
        if isinstance(item, dict)
    ]

    component_by_id = {
        str(component["id"]): component
        for component in components
        if component.get("id")
    }

    services = [
        {
            "id": str(component.get("id") or component.get("name")),
            "name": str(component.get("name") or component.get("id")),
        }
        for component in components
        if _component_type(component) in {"service", "microservice"}
    ]

    mappings = []
    mapped_services = set()
    confirmed_endpoints = set()
    candidate_endpoints = set()

    for operation in operations:
        method = str(
            operation.get("method") or "unknown"
        ).upper()

        path = str(operation.get("path") or "")
        endpoint = f"{method} {path}".strip()

        candidates = match_operation_to_services(
            operation,
            services
        )

        for candidate in candidates:
            mappings.append({
                "endpoint": endpoint,
                "operation_id": (
                    operation.get("operation_id")
                    or operation.get("operationId")
                ),
                **candidate,
                "score_interpretation": "heuristic_match_score",
            })

            mapped_services.add(
                candidate["candidate_service"]
            )

            if candidate.get("match_status") == "confirmed":
                confirmed_endpoints.add(endpoint)

            elif candidate.get("match_status") == "candidate":
                candidate_endpoints.add(endpoint)

    # Identificar dependencias entre servicios y componentes.
    dependencies = []

    for edge in _list(architecture.get("connections")):
        if not isinstance(edge, dict):
            continue

        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")

        if source not in component_by_id or target not in component_by_id:
            continue

        if _component_type(component_by_id[source]) not in {
            "service", "microservice"
        }:
            continue

        target_type = _component_type(
            component_by_id[target]
        )

        dependencies.append({
            "service": source,
            "dependency": target,
            "dependency_type": target_type,
            "relationship": edge.get("relationship") or "unknown",
            "direction": edge.get("direction") or "unknown",
            "source": "architecture_diagram",
            "evidence": edge.get("evidence") or "",

            # La flecha indica dependencia, pero no demuestra
            # necesariamente operaciones de lectura o escritura.
            "requires_review": target_type == "database",
        })

    # Identificar endpoints sin asociación.
    all_endpoints = {
        f"{str(operation.get('method') or 'unknown').upper()} "
        f"{str(operation.get('path') or '')}".strip()
        for operation in operations
    }

    unmapped_endpoints = sorted(
        all_endpoints
        - confirmed_endpoints
        - candidate_endpoints
    )

    # Identificar servicios sin asociación con endpoints.
    unmapped_services = sorted(
        service["id"]
        for service in services
        if service["id"] not in mapped_services
    )

    # Componentes arquitectónicos relacionados con dependencias.
    mapped_components = set(mapped_services)

    for dependency in dependencies:
        mapped_components.add(
            dependency["dependency"]
        )

    # Separar actores, gateways y otros componentes
    # de los servicios sin asociación.
    unmapped_architecture_components = sorted(
        component_id
        for component_id, component in component_by_id.items()
        if component_id not in mapped_components
        and _component_type(component) not in {
            "service", "microservice"
        }
    )

    # Registrar asociaciones que requieren validación.
    ambiguities = [
        {
            "element": mapping["endpoint"],
            "candidate": mapping["candidate_service"],
            "reason": (
                "Name/tag/path similarity does not prove "
                "service ownership."
            ),
        }
        for mapping in mappings
        if mapping.get("match_status") == "candidate"
    ]

    # Inferir el tipo de entrada OpenAPI cuando no está declarado.
    openapi_type = openapi.get("analysis_type")
    inferred_openapi_type = False

    if not openapi_type and (
        isinstance(openapi.get("operations"), list)
        or isinstance(openapi.get("paths"), dict)
    ):
        openapi_type = "openapi_contract"
        inferred_openapi_type = True

    warnings = []

    if not operations:
        warnings.append(
            "No OpenAPI operations were found."
        )

    if not services:
        warnings.append(
            "No service components were found."
        )

    if inferred_openapi_type:
        warnings.append(
            "OpenAPI analysis_type was inferred "
            "from the input structure."
        )

    return {
        "analysis_type": "contract_architecture_correlation",

        "sources": {
            "openapi_analysis_type": openapi_type,
            "architecture_analysis_type": architecture.get(
                "analysis_type"
            ),
            "architecture_model": architecture.get("model"),
        },

        "summary": {
            "total_operations": len(operations),
            "total_services": len(services),

            "total_endpoint_service_mappings": len(mappings),

            "confirmed_mappings": sum(
                mapping.get("match_status") == "confirmed"
                for mapping in mappings
            ),

            "candidate_mappings": sum(
                mapping.get("match_status") == "candidate"
                for mapping in mappings
            ),

            "unmapped_endpoints": len(unmapped_endpoints),
            "unmapped_services": len(unmapped_services),

            "unmapped_architecture_components": len(
                unmapped_architecture_components
            ),
        },

        "endpoint_service_mappings": mappings,

        "service_dependencies": dependencies,

        "unmapped_elements": {
            "endpoints": unmapped_endpoints,
            "services": unmapped_services,
            "architecture_components": (
                unmapped_architecture_components
            ),
        },

        "ambiguities": ambiguities,

        "warnings": warnings,

        "quality_note": (
            "Candidate mappings are heuristic, not proof of "
            "implementation ownership. A database arrow indicates "
            "a dependency but does not prove read/write semantics."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Correlate OpenAPI and architecture JSON files."
        )
    )

    parser.add_argument(
        "--openapi",
        required=True
    )

    parser.add_argument(
        "--architecture",
        required=True
    )

    parser.add_argument(
        "--output",
        default="correlation_analysis.json"
    )

    args = parser.parse_args()

    try:
        openapi = json.loads(
            Path(args.openapi).read_text(
                encoding="utf-8"
            )
        )

        architecture = json.loads(
            Path(args.architecture).read_text(
                encoding="utf-8"
            )
        )

    except (OSError, json.JSONDecodeError) as exc:
        raise CorrelationError(
            f"Could not load input JSON: {exc}"
        ) from exc

    result = correlate(
        openapi,
        architecture
    )

    Path(args.output).write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(
        f"Correlation analysis saved to: {args.output}"
    )


if __name__ == "__main__":
    main()