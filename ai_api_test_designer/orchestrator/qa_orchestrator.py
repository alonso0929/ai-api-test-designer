"""QA Orchestrator: coordinates the six AI API Test Designer tools.

Expected package modules:
- ai_api_test_designer.analyzers.openapi_analyzer
- ai_api_test_designer.analyzers.architecture_vision
- ai_api_test_designer.correlators.contract_architecture
- ai_api_test_designer.generators.test_case_generator
- ai_api_test_designer.coverage.coverage_engine
- ai_api_test_designer.reports.report_generator

The orchestrator delegates work to the existing tools; it does not duplicate
their analysis or generation logic.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


class OrchestrationError(RuntimeError):
    """Raised when a pipeline stage fails or its output is missing."""


def run_stage(
    name: str,
    command: Sequence[str],
    project_root: Path,
    expected_output: Path,
) -> dict:
    print(f"\n[START] {name}", flush=True)
    started = time.perf_counter()

    try:
        completed = subprocess.run(
            list(command),
            cwd=project_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise OrchestrationError(f"No se pudo iniciar '{name}': {exc}") from exc

    duration = round(time.perf_counter() - started, 2)

    if completed.stdout.strip():
        print(completed.stdout.strip(), flush=True)
    if completed.stderr.strip():
        print(completed.stderr.strip(), file=sys.stderr, flush=True)

    if completed.returncode != 0:
        raise OrchestrationError(
            f"La etapa '{name}' terminó con código {completed.returncode}."
        )

    if not expected_output.is_file():
        raise OrchestrationError(
            f"La etapa '{name}' terminó sin generar el archivo esperado: "
            f"{expected_output}"
        )

    print(f"[OK] {name} ({duration}s)", flush=True)
    return {
        "stage": name,
        "status": "completed",
        "duration_seconds": duration,
        "output": str(expected_output),
        "return_code": completed.returncode,
    }


def resolve_path(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def ensure_input(path: Path, label: str) -> None:
    if not path.is_file():
        raise OrchestrationError(f"No se encontró {label}: {path}")


def run_pipeline(args: argparse.Namespace) -> dict:
    project_root = Path(args.project_root).expanduser().resolve()
    if not project_root.is_dir():
        raise OrchestrationError(f"No existe el directorio del proyecto: {project_root}")

    openapi_file = resolve_path(args.openapi_file, project_root)
    architecture_image = resolve_path(args.architecture_image, project_root)
    ensure_input(openapi_file, "el contrato OpenAPI")
    ensure_input(architecture_image, "el diagrama de arquitectura")

    output_dir = resolve_path(args.output_dir, project_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts = {
        "openapi": output_dir / "openapi_analysis.json",
        "architecture": output_dir / "architecture_analysis.json",
        "correlation": output_dir / "correlation_analysis.json",
        "test_cases": output_dir / "test_cases.json",
        "coverage": output_dir / "coverage_report.json",
        "report_json": output_dir / "test_design_report.json",
        "report_markdown": output_dir / "test_design_report.md",
    }

    python = sys.executable
    stages = []

    # 1. Analyze the OpenAPI contract.
    stages.append(run_stage(
        "OpenAPI Analyzer",
        [
            python, "-m", "ai_api_test_designer.analyzers.openapi_analyzer",
            str(openapi_file), "--output", str(artifacts["openapi"]),
        ],
        project_root,
        artifacts["openapi"],
    ))

    # 2. Analyze the architecture diagram with the configured Ollama vision model.
    architecture_command = [
        python, "-m", "ai_api_test_designer.analyzers.architecture_vision",
        str(architecture_image),
        "--output", str(artifacts["architecture"]),
        "--model", args.model,
    ]
    stages.append(run_stage(
        "Architecture Vision Analyzer",
        architecture_command,
        project_root,
        artifacts["architecture"],
    ))

    # 3. Correlate contract operations with architecture components.
    stages.append(run_stage(
        "Contract-Architecture Correlator",
        [
            python, "-m", "ai_api_test_designer.correlators.contract_architecture",
            "--openapi", str(artifacts["openapi"]),
            "--architecture", str(artifacts["architecture"]),
            "--output", str(artifacts["correlation"]),
        ],
        project_root,
        artifacts["correlation"],
    ))

    # 4. Generate test cases. LLM suggestions remain reviewable candidates.
    stages.append(run_stage(
        "Test Case Generator",
        [
            python, "-m", "ai_api_test_designer.generators.test_case_generator",
            "--openapi", str(artifacts["openapi"]),
            "--architecture", str(artifacts["architecture"]),
            "--correlation", str(artifacts["correlation"]),
            "--output", str(artifacts["test_cases"]),
            "--model", args.model,
            "--ollama-url", args.ollama_url,
            "--timeout", str(args.timeout),
        ],
        project_root,
        artifacts["test_cases"],
    ))

    # 5. Calculate design coverage and traceability (not execution coverage).
    stages.append(run_stage(
        "Coverage & Traceability Engine",
        [
            python, "-m", "ai_api_test_designer.coverage.coverage_engine",
            "--openapi", str(artifacts["openapi"]),
            "--test-cases", str(artifacts["test_cases"]),
            "--correlation", str(artifacts["correlation"]),
            "--architecture", str(artifacts["architecture"]),
            "--output", str(artifacts["coverage"]),
        ],
        project_root,
        artifacts["coverage"],
    ))

    # 6. Consolidate all results into JSON and Markdown reports.
    stages.append(run_stage(
        "Report Generator",
        [
            python, "-m", "ai_api_test_designer.reports.report_generator",
            "--openapi", str(artifacts["openapi"]),
            "--architecture", str(artifacts["architecture"]),
            "--correlation", str(artifacts["correlation"]),
            "--test-cases", str(artifacts["test_cases"]),
            "--coverage", str(artifacts["coverage"]),
            "--output", str(artifacts["report_json"]),
            "--markdown", str(artifacts["report_markdown"]),
        ],
        project_root,
        artifacts["report_json"],
    ))
    if not artifacts["report_markdown"].is_file():
        raise OrchestrationError(
            f"Report Generator no creó el Markdown: {artifacts['report_markdown']}"
        )

    manifest = {
        "analysis_type": "qa_orchestration_execution",
        "status": "completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "project_root": str(project_root),
        "stages": stages,
        "artifacts": {key: str(value) for key, value in artifacts.items()},
        "semantics": {
            "coverage": "design_coverage_not_execution_coverage",
            "architecture_mappings": "candidate_mappings_require_human_validation",
        },
    }
    manifest_path = output_dir / "orchestration_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\n" + "=" * 58)
    print("QA ORCHESTRATOR COMPLETED")
    print(f"Stages completed: {len(stages)}/6")
    print(f"JSON report: {artifacts['report_json']}")
    print(f"Markdown report: {artifacts['report_markdown']}")
    print(f"Execution manifest: {manifest_path}")
    print("=" * 58)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Orquesta el flujo completo de AI API Test Designer."
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Raíz del proyecto que contiene el paquete ai_api_test_designer.",
    )
    parser.add_argument(
        "--openapi-file",
        required=True,
        help="Contrato OpenAPI original en JSON o YAML.",
    )
    parser.add_argument(
        "--architecture-image",
        required=True,
        help="Diagrama de arquitectura en PNG/JPG/JPEG.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts",
        help="Directorio donde se guardarán todos los resultados.",
    )
    parser.add_argument(
        "--model",
        default="qwen2.5vl:3b",
        help="Modelo Ollama para análisis visual y sugerencias de integración.",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="URL base del servicio Ollama.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=240,
        help="Timeout en segundos para las solicitudes al modelo.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        run_pipeline(args)
    except OrchestrationError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        print(
            "El flujo se detuvo para evitar generar un informe parcial como si fuera completo.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
