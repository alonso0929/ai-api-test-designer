
"""Vision-based architecture diagram analyzer using a local Ollama vision model."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import requests


class ArchitectureAnalysisError(Exception):
    """Raised when the diagram cannot be analyzed."""


COMPONENT_TYPES = {
    "actor",
    "api",
    "gateway",
    "database",
    "queue",
    "event_bus",
    "cache",
    "external_service",
    "client",
    "load_balancer",
    "identity_provider",
    "storage",
    "service",
    "unknown",
}

RELATIONSHIP_TYPES = {
    "calls",
    "reads_from",
    "writes_to",
    "publishes_to",
    "subscribes_to",
    "routes_to",
    "depends_on",
    "communicates_with",
    "interacts_with",
    "unknown",
}

DIRECTIONS = {"one_way", "two_way", "unknown"}


ANALYSIS_PROMPT = """
You are a senior software solution architect analyzing a
software architecture diagram.

Analyze ONLY what is visibly represented in the image.
Do not infer implementation details that are not shown.

Return ONLY valid JSON using this structure:

{
  "summary": "Short factual summary",
  "components": [
    {
      "id": "stable_id",
      "name": "visible name",
      "type": "actor|api|gateway|database|queue|event_bus|cache|external_service|client|load_balancer|identity_provider|storage|service|unknown",
      "description": "Description based only on visible information",
      "confidence": null,
      "evidence": "Visible label or visual cue"
    }
  ],
  "connections": [
    {
      "source": "component id",
      "target": "component id",
      "relationship": "calls|reads_from|writes_to|publishes_to|subscribes_to|routes_to|depends_on|communicates_with|interacts_with|unknown",
      "protocol": null,
      "direction": "one_way|two_way|unknown",
      "confidence": null,
      "evidence": "Specific description of the visible arrow or line"
    }
  ],
  "external_dependencies": [],
  "ambiguities": [],
  "warnings": []
}

COMPONENT RULES:

- A human or user represented outside the system should be type "actor".
- A mobile application or frontend should be type "client".
- An API Gateway should be type "gateway".
- An API should be type "api".
- A microservice should be type "service".
- A database should be type "database".
- Use the visible component name as its name.
- Do not invent components.
- Component IDs must be unique and stable.
- Describe only what can be observed.

CONNECTION RULES:

- Follow the actual arrow direction.
- An arrow from A to B means a one-way visual connection from A to B.
- Use "routes_to" when a gateway visibly directs traffic to a service.
- Use "interacts_with" when a service is connected to a database
  but the specific operation is not shown.
- Use "reads_from" only when reading is explicitly represented.
- Use "writes_to" only when writing is explicitly represented.
- Use "calls" only when a service call is explicitly indicated.
- Use "communicates_with" for a generic connection when its
  semantics cannot be determined.
- Never interpret every arrow as a write operation.
- Do not invent protocols, ports, authentication methods,
  or communication technologies.
- If arrow direction is unclear, use "unknown".
- Every source and target must reference an existing component ID.

CONFIDENCE AND EVIDENCE RULES:

- Confidence is an approximate model assessment, not a verified probability.
- Use null when confidence cannot be estimated reliably.
- Never return 0.0 merely because confidence is unknown.
- Evidence must describe a specific visible label, arrow,
  connection, or visual element.
- Do not use generic evidence such as "visible arrow or line".
- Never invent evidence.

OTHER RULES:

- Return an empty list when no elements can be identified.
- Explain uncertain interpretations in ambiguities.
- If this is not a software architecture diagram,
  return empty components and connections and explain why in warnings.
"""


class ArchitectureVisionAnalyzer:

    def __init__(self, ollama_url=None, model=None, timeout=600):
        self.ollama_url = (
            ollama_url
            or os.getenv("OLLAMA_URL", "http://localhost:11434")
        ).rstrip("/")

        self.model = (
            model
            or os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:3b")
        )

        self.timeout = timeout

    def analyze_file(self, image_path):
        path = Path(image_path)

        if not path.is_file():
            raise ArchitectureAnalysisError(
                f"Image file not found: {path}"
            )

        if path.suffix.lower() not in {
            ".png", ".jpg", ".jpeg"
        }:
            raise ArchitectureAnalysisError(
                "Supported formats: PNG, JPG and JPEG."
            )

        try:
            encoded = base64.b64encode(
                path.read_bytes()
            ).decode("ascii")

        except OSError as exc:
            raise ArchitectureAnalysisError(
                f"Could not read image: {exc}"
            ) from exc

        return self.analyze_base64(encoded)

    def analyze_base64(self, image_b64):

        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {
                    "role": "user",
                    "content": ANALYSIS_PROMPT,
                    "images": [image_b64]
                }
            ],
            "options": {
                "temperature": 0
            }
        }

        try:
            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=self.timeout
            )

            response.raise_for_status()
            body = response.json()

        except requests.RequestException as exc:
            raise ArchitectureAnalysisError(
                f"Could not reach Ollama at "
                f"{self.ollama_url}: {exc}"
            ) from exc

        except ValueError as exc:
            raise ArchitectureAnalysisError(
                "Ollama returned an invalid JSON response."
            ) from exc

        content = (
            body.get("message") or {}
        ).get("content")

        if not isinstance(content, str) or not content.strip():
            raise ArchitectureAnalysisError(
                "The vision model returned an empty response."
            )

        try:
            parsed = json.loads(content)

        except json.JSONDecodeError as exc:
            raise ArchitectureAnalysisError(
                "The model response was not valid JSON."
            ) from exc

        return self._normalize(parsed)

    def _normalize(self, data: Any):

        if not isinstance(data, dict):
            raise ArchitectureAnalysisError(
                "Architecture response must be a JSON object."
            )

        components = []
        valid_ids = set()
        warnings = self._string_list(data.get("warnings"))

        # Normalize components
        for index, item in enumerate(
            self._list(data.get("components"))
        ):

            if not isinstance(item, dict):
                continue

            name = str(
                item.get("name") or
                f"Unknown component {index + 1}"
            ).strip()

            component_id = str(
                item.get("id") or
                f"component_{index + 1}"
            ).strip()

            if not component_id:
                component_id = f"component_{index + 1}"

            if component_id in valid_ids:
                warnings.append(
                    f"Duplicate component ID ignored: {component_id}"
                )
                continue

            component_type = str(
                item.get("type") or "unknown"
            ).strip().lower()

            if component_type not in COMPONENT_TYPES:
                warnings.append(
                    f"Unknown component type '{component_type}' "
                    f"for component {component_id}."
                )
                component_type = "unknown"

            valid_ids.add(component_id)

            components.append({
                "id": component_id,
                "name": name,
                "type": component_type,
                "description": str(
                    item.get("description") or ""
                ),
                "confidence": self._confidence(
                    item.get("confidence")
                ),
                "evidence": str(
                    item.get("evidence") or ""
                )
            })

        # Normalize connections
        connections = []

        for item in self._list(data.get("connections")):

            if not isinstance(item, dict):
                continue

            source = str(item.get("source") or "").strip()
            target = str(item.get("target") or "").strip()

            if source not in valid_ids or target not in valid_ids:
                warnings.append(
                    f"Connection ignored: unknown component "
                    f"endpoint {source} -> {target}"
                )
                continue

            relationship = str(
                item.get("relationship") or "unknown"
            ).strip().lower()

            if relationship not in RELATIONSHIP_TYPES:
                warnings.append(
                    f"Unknown relationship '{relationship}' "
                    f"for {source} -> {target}."
                )
                relationship = "unknown"

            direction = str(
                item.get("direction") or "unknown"
            ).strip().lower()

            if direction not in DIRECTIONS:
                direction = "unknown"

            connections.append({
                "source": source,
                "target": target,
                "relationship": relationship,
                "protocol": item.get("protocol"),
                "direction": direction,
                "confidence": self._confidence(
                    item.get("confidence")
                ),
                "evidence": str(
                    item.get("evidence") or ""
                )
            })

        return {
            "analysis_type": "architecture_diagram",
            "model": self.model,
            "summary": str(data.get("summary") or ""),
            "components": components,
            "connections": connections,
            "external_dependencies": self._string_list(
                data.get("external_dependencies")
            ),
            "ambiguities": self._string_list(
                data.get("ambiguities")
            ),
            "warnings": warnings,
            "quality_note": (
                "Model interpretations must be reviewed against "
                "the original diagram. Visual connections do not "
                "prove protocols, business rules, or implementation "
                "details."
            )
        }

    @staticmethod
    def _list(value):
        return value if isinstance(value, list) else []

    @staticmethod
    def _string_list(value):
        if not isinstance(value, list):
            return []

        return [
            str(item)
            for item in value
            if item is not None
        ]

    @staticmethod
    def _confidence(value):

        if value is None:
            return None

        try:
            return max(
                0.0,
                min(1.0, float(value))
            )

        except (TypeError, ValueError):
            return None


def main():

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Analyze an architecture image with Ollama vision."
        )
    )

    parser.add_argument(
        "image",
        help="PNG/JPG/JPEG architecture diagram"
    )

    parser.add_argument(
        "--output",
        default="architecture_analysis.json"
    )

    parser.add_argument(
        "--model",
        help="Ollama vision model; overrides OLLAMA_VISION_MODEL"
    )

    args = parser.parse_args()

    analyzer = ArchitectureVisionAnalyzer(
        model=args.model
    )

    result = analyzer.analyze_file(args.image)

    Path(args.output).write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(
        f"Architecture analysis saved to: {args.output}"
    )


if __name__ == "__main__":
    main()
