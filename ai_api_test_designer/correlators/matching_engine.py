import re

def normalize_name(value):
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(value or ""))
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    result = []
    for token in tokens:
        if len(token) > 4 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        result.append(token)
    return " ".join(result)

def match_operation_to_services(operation, services):
    explicit = next((operation.get(k) for k in
        ("x-service-name", "x-owner-service", "x-backend-service")
        if isinstance(operation.get(k), str) and operation[k].strip()), None)
    fields = [str(operation.get("path") or ""),
              str(operation.get("operation_id") or ""),
              *[str(x) for x in (operation.get("tags") or [])]]
    normalized_fields = [(f, normalize_name(f)) for f in fields if f]
    matches = []
    for service in services:
        sid = str(service.get("id") or service.get("name") or "")
        name = str(service.get("name") or sid)
        normalized = normalize_name(name)
        if explicit and normalize_name(explicit) == normalized:
            matches.append({"candidate_service": sid,
                "match_method": "explicit_extension", "match_status": "confirmed",
                "evidence": [f"OpenAPI explicitly declares service '{explicit}'."],
                "requires_review": False, "score": 1.0})
            continue
        tokens = set(normalized.split())
        evidence, score = [], 0.0
        for original, field in normalized_fields:
            overlap = tokens & set(field.split())
            if overlap:
                evidence.append(f"Token overlap '{', '.join(sorted(overlap))}' between service '{name}' and '{original}'.")
                score += 0.5 if original in (operation.get("tags") or []) else 0.35
        if evidence:
            matches.append({"candidate_service": sid,
                "match_method": "name_tag_path_similarity", "match_status": "candidate",
                "evidence": evidence, "requires_review": True, "score": min(score, 0.95)})
    return sorted(matches, key=lambda x: x["score"], reverse=True)
