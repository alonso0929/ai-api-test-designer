import json
from pathlib import Path
from typing import Any
import yaml

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}

class OpenAPIAnalysisError(Exception):
    pass

class OpenAPIAnalyzer:
    """Deterministic OpenAPI 3.x parser. No LLM calls are made here."""

    def analyze_file(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        if not path.is_file():
            raise OpenAPIAnalysisError(f"File not found: {path}")
        try:
            raw = path.read_text(encoding="utf-8-sig")
            doc = json.loads(raw) if path.suffix.lower() == ".json" else yaml.safe_load(raw)
        except Exception as exc:
            raise OpenAPIAnalysisError(f"Cannot parse contract: {exc}") from exc
        return self.analyze_document(doc)

    def analyze_document(self, doc: Any) -> dict[str, Any]:
        if not isinstance(doc, dict) or not str(doc.get("openapi", "")).startswith("3."):
            raise OpenAPIAnalysisError("A valid OpenAPI 3.x document is required.")

        validation = self._validate(doc)
        operations = []
        for path, item in (doc.get("paths") or {}).items():
            if not isinstance(item, dict):
                continue
            for method, op in item.items():
                if method.lower() in HTTP_METHODS and isinstance(op, dict):
                    operations.append(self._operation(doc, path, method.upper(), op, item.get("parameters", [])))
        operations.sort(key=lambda x: (x["path"], x["method"]))

        method_counts = {}
        tags, codes = set(), set()
        parameter_count = secured = deprecated = request_properties = 0
        for op in operations:
            method_counts[op["method"]] = method_counts.get(op["method"], 0) + 1
            tags.update(op["tags"])
            codes.update(r["status_code"] for r in op["responses"])
            parameter_count += len(op["parameters"])
            secured += bool(op["security"])
            deprecated += op["deprecated"]
            request_properties += sum(len(c["schema"]["properties"]) for c in op["request_body"]["content"])

        info = doc.get("info") or {}
        return {
            "contract": {
                "title": info.get("title", "Untitled API"),
                "version": info.get("version", "unspecified"),
                "openapi_version": doc["openapi"],
                "servers": [s.get("url") for s in doc.get("servers", []) if isinstance(s, dict)],
            },
            "validation": validation,
            "inventory": {
                "endpoint_count": len(operations),
                "method_counts": dict(sorted(method_counts.items())),
                "tags": sorted(tags),
                "parameter_count": parameter_count,
                "request_body_property_count": request_properties,
                "response_status_codes": sorted(codes),
                "secured_operation_count": secured,
                "deprecated_operation_count": deprecated,
            },
            "operations": operations,
            "analysis_scope": {
                "included": ["methods and paths", "parameters", "request and response schemas",
                             "required fields, enums, formats and constraints", "security and tags"],
                "limitations": ["External $ref files are not resolved.",
                                "Business rules absent from the contract cannot be inferred.",
                                "Structural inventory is not proof of executed test coverage."]
            }
        }

    def _validate(self, doc):
        try:
            from openapi_spec_validator import validate
            validate(doc)
            return {"valid": True, "validator": "openapi-spec-validator", "errors": []}
        except ImportError:
            return {"valid": None, "validator": "not-installed",
                    "errors": ["Install openapi-spec-validator to validate the specification."]}
        except Exception as exc:
            return {"valid": False, "validator": "openapi-spec-validator", "errors": [str(exc)]}

    def _resolve(self, doc, obj, depth=0):
        if depth > 20 or not isinstance(obj, dict) or "$ref" not in obj:
            return obj
        ref = obj["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return {"$ref": ref, "description": "External reference not resolved"}
        target = doc
        try:
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            return {"$ref": ref, "description": "Unresolved local reference"}
        if not isinstance(target, dict):
            return target
        merged = dict(target)
        merged.update({k: v for k, v in obj.items() if k != "$ref"})
        return self._resolve_nested(doc, merged, depth + 1)

    def _resolve_nested(self, doc, value, depth=0):
        if depth > 20:
            return value
        if isinstance(value, dict):
            return self._resolve(doc, value, depth) if "$ref" in value else {
                k: self._resolve_nested(doc, v, depth + 1) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_nested(doc, v, depth + 1) for v in value]
        return value

    def _schema(self, schema):
        if not isinstance(schema, dict):
            return {"type": "unspecified", "required_fields": [], "properties": []}
        required = set(schema.get("required") or [])
        props = []
        for name, p in (schema.get("properties") or {}).items():
            p = p if isinstance(p, dict) else {}
            props.append({
                "name": name, "type": p.get("type", "unspecified"),
                "format": p.get("format"), "required": name in required,
                "enum": p.get("enum"), "minimum": p.get("minimum"), "maximum": p.get("maximum"),
                "min_length": p.get("minLength"), "max_length": p.get("maxLength"),
                "pattern": p.get("pattern"), "nullable": p.get("nullable", False),
            })
        return {
            "type": schema.get("type", "unspecified"), "format": schema.get("format"),
            "description": schema.get("description", ""), "required_fields": sorted(required),
            "properties": props, "enum": schema.get("enum"), "minimum": schema.get("minimum"),
            "maximum": schema.get("maximum"), "min_length": schema.get("minLength"),
            "max_length": schema.get("maxLength"), "pattern": schema.get("pattern"),
            "one_of_count": len(schema.get("oneOf", [])),
            "any_of_count": len(schema.get("anyOf", [])),
            "all_of_count": len(schema.get("allOf", [])),
        }

    def _content(self, doc, content):
        result = []
        for media_type, media in (content or {}).items():
            if isinstance(media, dict):
                schema = self._resolve_nested(doc, media.get("schema") or {})
                result.append({"media_type": media_type, "schema": self._schema(schema)})
        return result

    def _operation(self, doc, path, method, op, path_params):
        params, seen = [], set()
        for raw in list(path_params or []) + list(op.get("parameters", []) or []):
            p = self._resolve(doc, raw)
            if not isinstance(p, dict):
                continue
            key = (p.get("name"), p.get("in"))
            if key in seen:
                continue
            seen.add(key)
            params.append({"name": p.get("name"), "in": p.get("in"),
                           "required": bool(p.get("required")),
                           "schema": self._schema(self._resolve_nested(doc, p.get("schema") or {}))})
        body = self._resolve(doc, op.get("requestBody", {}))
        body = body if isinstance(body, dict) else {}
        responses = []
        for status, raw in (op.get("responses") or {}).items():
            response = self._resolve(doc, raw)
            if isinstance(response, dict):
                responses.append({"status_code": str(status), "description": response.get("description", ""),
                                  "content": self._content(doc, response.get("content", {}))})
        return {
            "operation_id": op.get("operationId"), "summary": op.get("summary", ""),
            "description": op.get("description", ""), "path": path, "method": method,
            "tags": op.get("tags", []), "deprecated": bool(op.get("deprecated", False)),
            "parameters": params,
            "request_body": {"required": bool(body.get("required")),
                             "content": self._content(doc, body.get("content", {}))},
            "responses": sorted(responses, key=lambda r: r["status_code"]),
            "security": op.get("security", doc.get("security", [])) or [],
        }

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze an OpenAPI 3.x JSON/YAML contract")
    parser.add_argument("file")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = OpenAPIAnalyzer().analyze_file(args.file)
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered)

if __name__ == "__main__":
    main()
