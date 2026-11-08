import argparse
import json
import re
import uuid
import urllib.request
import urllib.error
from pathlib import Path


class TestCaseGenerationError(Exception):
    pass


VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"
NON_EXISTENT_UUID = "550e8400-e29b-41d4-a716-446655440099"
INVALID_UUID = "not-a-valid-uuid"


def load_json(path):
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TestCaseGenerationError(f"Error loading {path}: {exc}") from exc


def response_codes(operation):
    return {
        str(response.get("status_code"))
        for response in operation.get("responses", [])
        if response.get("status_code") is not None
    }


def documented_code(operation, preferred, fallback=None):
    codes = response_codes(operation)
    if str(preferred) in codes:
        return int(preferred)
    if fallback is not None and str(fallback) in codes:
        return int(fallback)
    return None


def get_body_schema(operation):
    body = operation.get("request_body") or {}
    for item in body.get("content", []):
        schema = item.get("schema")
        if isinstance(schema, dict):
            return schema
    return None


def property_map(schema):
    return {
        prop.get("name"): prop
        for prop in (schema or {}).get("properties", [])
        if prop.get("name")
    }


def sample_value(prop):
    if prop.get("enum"):
        return prop["enum"][0]
    fmt = prop.get("format")
    typ = prop.get("type")
    if fmt == "uuid":
        return VALID_UUID
    if typ == "integer":
        return int(prop.get("minimum", 1))
    if typ == "number":
        return prop.get("minimum", 1) if prop.get("minimum") is not None else 1
    if typ == "boolean":
        return True
    if typ == "array":
        return []
    if typ == "object":
        return {}
    min_length = prop.get("min_length")
    if min_length:
        return "a" * min_length
    return "texto de prueba"


def valid_body(schema):
    props = property_map(schema)
    required = (schema or {}).get("required_fields", [])
    data = {}
    for name, prop in props.items():
        if name in required or prop.get("required"):
            data[name] = sample_value(prop)
    return data


def make_case(operation, title, category, test_data, expected_code,
              expected_result, steps, preconditions=None, assumptions=None,
              source_elements=None, test_type="functional"):
    method = operation.get("method", "GET").upper()
    path = operation.get("path", "")
    operation_id = operation.get("operation_id")
    return {
        "id": "",
        "title": title,
        "endpoint": f"{method} {path}",
        "operation_id": operation_id,
        "category": category,
        "test_type": test_type,
        "priority": "high" if category in ("negative", "security") else "medium",
        "preconditions": preconditions or [],
        "test_data": test_data,
        "steps": steps,
        "expected_status_code": expected_code,
        "expected_result": expected_result,
        "gherkin": {
            "given": (preconditions or ["La API está disponible"])[0],
            "when": steps[0] if steps else "Se envía la solicitud",
            "then": expected_result,
        },
        "source": {
            "artifact": "openapi",
            "elements": [operation_id] + (source_elements or []),
        },
        "assumptions": assumptions or [],
        "contract_violations": [],
    }


def generate_body_cases(operation):
    schema = get_body_schema(operation)
    if not schema:
        return []

    props = property_map(schema)
    required = list(schema.get("required_fields", []))
    body = valid_body(schema)
    success_code = documented_code(operation, 201, 200)
    error_code = documented_code(operation, 400)
    cases = []
    endpoint = operation.get("path", "")

    cases.append(make_case(
        operation,
        "Crear recurso con datos válidos",
        "positive", body, success_code,
        f"La API acepta la solicitud y responde con HTTP {success_code}." if success_code else "La API acepta la solicitud según el contrato.",
        [f"Enviar una solicitud {operation.get('method', 'POST').upper()} a {endpoint} con el body indicado.", "Verificar el código HTTP y la estructura de la respuesta."],
        ["Se dispone de un token de autenticación válido."],
        source_elements=["request_body", "required_fields"],
    ))

    # Boundary-value scenarios are derived from declared constraints.
    for name, prop in props.items():
        # Optional fields are tested when they declare constraints too.
        base_for_prop = dict(body)
        if name not in base_for_prop:
            base_for_prop[name] = sample_value(prop)
        minimum = prop.get("minimum")
        maximum = prop.get("maximum")
        if minimum is not None:
            boundary_body = dict(base_for_prop)
            boundary_body[name] = minimum
            cases.append(make_case(
                operation, f"Aceptar valor mínimo de {name}", "positive",
                boundary_body, success_code,
                f"La API acepta {name} en su valor mínimo permitido ({minimum}).",
                [f"Enviar {name} = {minimum} en {endpoint}.", "Verificar que la solicitud sea aceptada."],
                ["Se dispone de un token válido."], source_elements=[f"minimum:{name}"],
            ))
            invalid_body = dict(base_for_prop)
            invalid_body[name] = minimum - 1 if isinstance(minimum, (int, float)) else minimum
            if isinstance(minimum, (int, float)):
                cases.append(make_case(
                    operation, f"Rechazar valor inferior al mínimo de {name}", "negative",
                    invalid_body, error_code,
                    f"La API rechaza el valor inferior al mínimo; se espera HTTP {error_code}." if error_code else "La API rechaza el valor; el contrato no documenta el código HTTP para este caso.",
                    [f"Enviar {name} = {invalid_body[name]} en {endpoint}.", "Verificar el rechazo de la solicitud."],
                    ["Se dispone de un token válido."],
                    assumptions=[] if error_code else ["El contrato no especifica el código HTTP para esta validación."],
                    source_elements=[f"below_minimum:{name}"],
                ))
        if maximum is not None:
            boundary_body = dict(base_for_prop)
            boundary_body[name] = maximum
            cases.append(make_case(
                operation, f"Aceptar valor máximo de {name}", "positive",
                boundary_body, success_code,
                f"La API acepta {name} en su valor máximo permitido ({maximum}).",
                [f"Enviar {name} = {maximum} en {endpoint}.", "Verificar que la solicitud sea aceptada."],
                ["Se dispone de un token válido."], source_elements=[f"maximum:{name}"],
            ))
            if isinstance(maximum, (int, float)):
                invalid_body = dict(body)
                invalid_body[name] = maximum + 1
                cases.append(make_case(
                    operation, f"Rechazar valor superior al máximo de {name}", "negative",
                    invalid_body, error_code,
                    f"La API rechaza el valor superior al máximo; se espera HTTP {error_code}." if error_code else "La API rechaza el valor; el contrato no documenta el código HTTP para este caso.",
                    [f"Enviar {name} = {invalid_body[name]} en {endpoint}.", "Verificar el rechazo de la solicitud."],
                    ["Se dispone de un token válido."],
                    assumptions=[] if error_code else ["El contrato no especifica el código HTTP para esta validación."],
                    source_elements=[f"above_maximum:{name}"],
                ))
        enum = prop.get("enum")
        if enum:
            for allowed in enum:
                enum_body = dict(base_for_prop)
                enum_body[name] = allowed
                cases.append(make_case(
                    operation, f"Aceptar {name} permitido: {allowed}", "positive",
                    enum_body, success_code,
                    f"La API acepta el valor permitido {allowed} para {name}.",
                    [f"Enviar {name} = {allowed} en {endpoint}.", "Verificar que la solicitud sea aceptada."],
                    ["Se dispone de un token válido."], source_elements=[f"enum:{name}:{allowed}"],
                ))
            invalid_body = dict(base_for_prop)
            invalid_body[name] = "VALOR_NO_PERMITIDO"
            cases.append(make_case(
                operation, f"Rechazar valor no permitido para {name}", "negative",
                invalid_body, error_code,
                f"La API rechaza el valor fuera del enum; se espera HTTP {error_code}." if error_code else "La API rechaza el valor fuera del enum.",
                [f"Enviar {name} = VALOR_NO_PERMITIDO en {endpoint}.", "Verificar el rechazo de la solicitud."],
                ["Se dispone de un token válido."],
                assumptions=[] if error_code else ["El contrato no especifica el código HTTP para este caso."],
                source_elements=[f"enum_violation:{name}"],
            ))
        max_length = prop.get("max_length")
        if max_length is not None:
            boundary_body = dict(base_for_prop)
            boundary_body[name] = "a" * max_length
            cases.append(make_case(
                operation, f"Aceptar longitud máxima de {name}", "positive",
                boundary_body, success_code,
                f"La API acepta {name} con {max_length} caracteres.",
                [f"Enviar {name} con exactamente {max_length} caracteres.", "Verificar que la solicitud sea aceptada."],
                ["Se dispone de un token válido."], source_elements=[f"max_length:{name}"],
            ))
            invalid_body = dict(base_for_prop)
            invalid_body[name] = "a" * (max_length + 1)
            cases.append(make_case(
                operation, f"Rechazar longitud superior al máximo de {name}", "negative",
                invalid_body, error_code,
                f"La API rechaza {name} por superar {max_length} caracteres." ,
                [f"Enviar {name} con {max_length + 1} caracteres.", "Verificar el rechazo de la solicitud."],
                ["Se dispone de un token válido."],
                assumptions=[] if error_code else ["El contrato no especifica el código HTTP para este caso."],
                source_elements=[f"max_length_exceeded:{name}"],
            ))

    for name in required:
        if name in body:
            missing_body = dict(body)
            missing_body.pop(name, None)
            cases.append(make_case(
                operation, f"Rechazar solicitud sin campo obligatorio {name}", "negative",
                missing_body, error_code,
                f"La API rechaza la solicitud por ausencia de {name}." ,
                [f"Enviar la solicitud a {endpoint} sin el campo {name}.", "Verificar el rechazo de la solicitud."],
                ["Se dispone de un token válido."],
                assumptions=[] if error_code else ["El contrato no especifica el código HTTP para este caso."],
                source_elements=[f"required_missing:{name}"],
            ))

    return cases


def generate_parameter_cases(operation):
    cases = []
    success_code = documented_code(operation, 200, 201)
    not_found_code = documented_code(operation, 404)
    error_code = documented_code(operation, 400)
    endpoint = operation.get("path", "")

    for parameter in operation.get("parameters", []):
        if parameter.get("in") != "path":
            continue
        name = parameter.get("name")
        schema = parameter.get("schema", {})
        fmt = schema.get("format")
        if fmt == "uuid":
            cases.append(make_case(
                operation, f"Consultar recurso existente con {name} válido", "positive",
                {name: VALID_UUID}, success_code,
                f"La API devuelve el recurso y responde HTTP {success_code}." if success_code else "La API devuelve el recurso según el contrato.",
                [f"Enviar GET a {endpoint.replace('{' + name + '}', VALID_UUID)}.", "Verificar la respuesta y el código HTTP."],
                ["Existe un recurso asociado al UUID utilizado.", "Se dispone de un token válido."],
                assumptions=["El UUID de prueba debe estar previamente registrado en el entorno."],
                source_elements=[f"format:{name}:uuid"],
            ))
            cases.append(make_case(
                operation, f"Consultar recurso inexistente con {name} válido", "negative",
                {name: NON_EXISTENT_UUID}, not_found_code,
                f"La API responde HTTP {not_found_code} porque el recurso no existe." if not_found_code else "La API informa que el recurso no existe; el contrato no documenta un código 404.",
                [f"Enviar GET a {endpoint.replace('{' + name + '}', NON_EXISTENT_UUID)}.", "Verificar la respuesta de recurso no encontrado."],
                ["El UUID tiene formato válido, pero no está registrado.", "Se dispone de un token válido."],
                assumptions=[] if not_found_code else ["El contrato no documenta un código HTTP 404."],
                source_elements=[f"not_found:{name}"],
            ))
            cases.append(make_case(
                operation, f"Rechazar formato UUID inválido en {name}", "negative",
                {name: INVALID_UUID}, error_code,
                f"La API rechaza el formato UUID inválido con HTTP {error_code}." if error_code else "La API rechaza el formato UUID inválido; el contrato no documenta el código HTTP.",
                [f"Enviar GET a {endpoint.replace('{' + name + '}', INVALID_UUID)}.", "Verificar que la API rechace el parámetro."],
                ["Se dispone de un token válido."],
                assumptions=[] if error_code else ["El contrato no documenta el código HTTP para UUID inválido."],
                source_elements=[f"invalid_format:{name}:uuid"],
            ))
        else:
            value = sample_value(schema)
            cases.append(make_case(
                operation, f"Consultar recurso con parámetro {name} válido", "positive",
                {name: value}, success_code,
                "La API devuelve el recurso solicitado.",
                [f"Enviar la solicitud a {endpoint} con {name} = {value}.", "Verificar la respuesta."],
                ["Se dispone de un token válido."], source_elements=[f"parameter:{name}"],
            ))
    return cases


def generate_security_case(operation):
    if not operation.get("security"):
        return None
    unauthorized = documented_code(operation, 401)
    method = operation.get("method", "GET").upper()
    path = operation.get("path", "")
    return make_case(
        operation, "Rechazar solicitud sin credenciales de autenticación", "security",
        {"authorization": None}, unauthorized,
        f"La API rechaza la solicitud sin token y responde HTTP {unauthorized}." if unauthorized else "La API rechaza la solicitud sin credenciales; el contrato no documenta HTTP 401.",
        [f"Enviar {method} a {path} sin el encabezado Authorization.", "Verificar que el acceso sea rechazado."],
        ["El endpoint requiere autenticación según el esquema de seguridad del contrato."],
        assumptions=[] if unauthorized else ["El contrato no documenta un código HTTP 401."],
        source_elements=["security", "missing_bearer_token"],
        test_type="security",
    )


def deduplicate(cases):
    unique = []
    seen = set()
    for case in cases:
        signature = (
            case["operation_id"], case["title"],
            json.dumps(case["test_data"], sort_keys=True, ensure_ascii=False),
        )
        if signature not in seen:
            seen.add(signature)
            unique.append(case)
    return unique


def ollama_json(prompt, model, ollama_url, timeout):
    """Call Ollama for architecture-informed suggestions; never let it override contract rules."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": (
                "Eres un QA senior. Responde exclusivamente JSON válido. "
                "No inventes reglas de negocio, endpoints, componentes ni códigos HTTP. "
                "Si la relación es candidata o requiere revisión, indícalo claramente."
            )},
            {"role": "user", "content": prompt},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 900},
    }
    request = urllib.request.Request(
        ollama_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw.get("message", {}).get("content", "{}")
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        raise TestCaseGenerationError(f"No se pudo obtener una respuesta JSON de Ollama: {exc}") from exc


def architecture_suggestions(operation, architecture, correlation, model, ollama_url, timeout):
    """Ask the LLM for reviewable integration scenarios using only candidate correlations."""
    if not correlation or not model:
        return []
    op_id = operation.get("operation_id")
    mappings = [m for m in correlation.get("endpoint_service_mappings", [])
                if m.get("operation_id") == op_id]
    if not mappings:
        return []
    dependencies = correlation.get("service_dependencies", [])
    context = {
        "architecture_analysis": architecture or {},
        "mappings": mappings,
        "service_dependencies": dependencies,
    }
    prompt = (
        "Actúa como ingeniero QA senior especializado en pruebas de integración de APIs. "
        "Responde exclusivamente en español y devuelve únicamente JSON válido. "
        "Propón como máximo 2 escenarios distintos y útiles para esta operación. "
        "Usa solamente componentes, relaciones y datos que aparezcan explícitamente en el contexto. "
        "No inventes rutas entre servicios, reglas de negocio, datos de respuesta ni códigos HTTP. "
        "Una conexión dibujada no demuestra por sí sola una lectura o escritura en una base de datos. "
        "No afirmes persistencia, consulta, autorización ni creación en una base de datos salvo que "
        "la evidencia lo indique expresamente. Si el mapeo no está confirmado, el escenario debe "
        "quedar marcado para revisión. Incluye datos de prueba coherentes con el contrato. "
        "Evita repetir el mismo flujo con otro título. "
        "Devuelve este JSON: {\"scenarios\":[{\"title\":str,\"preconditions\":[str],"
        "\"steps\":[str],\"expected_result\":str,\"evidence\":[str]}]}. "
        "Operación: " + json.dumps(operation, ensure_ascii=False) +
        " Contexto de arquitectura y correlación: " + json.dumps(context, ensure_ascii=False)
    )
    result = ollama_json(prompt, model, ollama_url, timeout)
    scenarios = result.get("scenarios", [])
    if not isinstance(scenarios, list):
        return []
    mapping = mappings[0]
    service = mapping.get("candidate_service")
    review = mapping.get("match_status") != "confirmed" or mapping.get("requires_review", False)
    output = []
    for scenario in scenarios[:2]:
        if not isinstance(scenario, dict):
            continue
        title = str(scenario.get("title", "")).strip()
        steps = scenario.get("steps", [])
        if not title or not isinstance(steps, list) or not steps:
            continue
        preconditions = scenario.get("preconditions", [])
        evidence = scenario.get("evidence", [])

        # Completar los datos desde el contrato OpenAPI, sin inventar valores.
        test_data = {}
        body_schema = get_body_schema(operation)
        if body_schema:
            test_data.update(valid_body(body_schema))
        for parameter in operation.get("parameters", []):
            if parameter.get("in") == "path" and parameter.get("name"):
                test_data[parameter["name"]] = sample_value(parameter.get("schema", {}))

        expected_result = str(
            scenario.get("expected_result") or
            "Validar la interacción entre los componentes identificados en el diagrama."
        ).strip()
        if re.search(r"HTTP\\s*\\d{3}|código\\s*\\d{3}", expected_result, re.IGNORECASE):
            expected_result = (
                "Verificar el resultado de la interacción entre los componentes; "
                "el contrato no permite establecer aquí un código HTTP adicional."
            )

        output.append(make_case(
            operation,
            title,
            "integration_candidate",
            test_data,
            None,
            expected_result,
            [str(step).strip() for step in steps[:5]],
            [str(item).strip() for item in preconditions[:4]] if isinstance(preconditions, list) else [],
            assumptions=[
                f"El servicio {service} es una correlación candidata y requiere confirmación."
                if review else f"Servicio asociado según la correlación: {service}.",
                "Validar con arquitectura o con el equipo responsable cualquier interacción no confirmada."
            ],
            source_elements=["architecture_diagram", f"candidate_service:{service}"],
            test_type="integration",
        ) | {
            "requires_review": review,
            "architecture_evidence": [str(item) for item in evidence[:6]] if isinstance(evidence, list) else []
        })
    # Eliminar escenarios repetidos con los mismos pasos para la misma operación.
    unique_output = []
    seen_scenarios = set()
    for case in output:
        signature = (
            case.get("operation_id"),
            tuple(step.lower().strip() for step in case.get("steps", [])),
        )
        if signature not in seen_scenarios:
            seen_scenarios.add(signature)
            unique_output.append(case)
    return unique_output


def generate_test_cases(openapi, architecture=None, correlation=None, model=None,
                        ollama_url="http://localhost:11434", timeout=240):
    if not isinstance(openapi, dict) or not isinstance(openapi.get("operations"), list):
        raise TestCaseGenerationError("OpenAPI analysis must contain an operations array.")

    operations = openapi["operations"]
    all_cases = []
    analyzed = []
    for operation in operations:
        operation_id = operation.get("operation_id") or f"{operation.get('method', 'GET')} {operation.get('path', '')}"
        analyzed.append(operation_id)
        operation_cases = []
        operation_cases.extend(generate_body_cases(operation))
        operation_cases.extend(generate_parameter_cases(operation))
        security_case = generate_security_case(operation)
        if security_case:
            operation_cases.append(security_case)
        # Qwen proposes architecture-informed integration cases; Python keeps contract cases authoritative.
        if model and correlation:
            operation_cases.extend(architecture_suggestions(
                operation, architecture, correlation, model, ollama_url, timeout
            ))
        all_cases.extend(deduplicate(operation_cases))

    for index, case in enumerate(all_cases, start=1):
        case["id"] = f"TC-{index:03d}"

    covered = sorted({case["operation_id"] for case in all_cases if case.get("operation_id")})
    counts = {
        "total_test_cases": len(all_cases),
        "positive_cases": sum(c["category"] == "positive" for c in all_cases),
        "negative_cases": sum(c["category"] == "negative" for c in all_cases),
        "security_cases": sum(c["category"] == "security" for c in all_cases),
        "integration_candidate_cases": sum(c["category"] == "integration_candidate" for c in all_cases),
    }

    return {
        "analysis_type": "test_case_generation",
        "summary": counts,
        "test_cases": all_cases,
        "coverage": {
            "operations_analyzed": analyzed,
            "operations_with_test_cases": covered,
            "uncovered_operations": [op for op in analyzed if op not in covered],
            "coverage_type": "design_coverage_not_execution_coverage",
        },
        "assumptions": [
            "Los datos de prueba que requieren registros existentes deben prepararse en el entorno.",
            "Los códigos HTTP esperados se incluyen únicamente cuando están documentados en OpenAPI.",
        ],
        "limitations": [
            "La generación funcional se basa en restricciones estructurales extraídas del contrato OpenAPI.",
            "No se infieren reglas de negocio que no estén documentadas.",
            "Los casos generados no han sido ejecutados contra la API.",
            "Los escenarios de integración propuestos por IA requieren revisión cuando la correlación no está confirmada.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Generate API test cases from normalized OpenAPI analysis.")
    parser.add_argument("--openapi", required=True, help="Path to openapi_analysis.json")
    parser.add_argument("--architecture", help="Optional architecture analysis JSON")
    parser.add_argument("--correlation", help="Optional contract-architecture correlation JSON")
    parser.add_argument("--output", default="test_cases.json")
    parser.add_argument("--model", default=None, help="Ollama model for architecture-aware integration suggestions")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    openapi = load_json(args.openapi)
    architecture = load_json(args.architecture)
    correlation = load_json(args.correlation)
    result = generate_test_cases(
        openapi, architecture, correlation, args.model, args.ollama_url, args.timeout
    )
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Generated {result['summary']['total_test_cases']} test cases.")
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    print(f"Output saved to: {args.output}")


if __name__ == "__main__":
    main()
