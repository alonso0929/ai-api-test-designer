# AI API Test Designer

Herramienta de diseño de pruebas de API basada en inteligencia artificial. Analiza contratos OpenAPI y diagramas de arquitectura de software para generar casos de prueba estructurados, análisis de cobertura, trazabilidad e informes de QA.

El proyecto combina análisis determinístico e inteligencia artificial generativa para asistir en el proceso de diseño de pruebas.

## Características

La solución integra seis módulos coordinados por el QA Orchestrator:

1. **OpenAPI Analyzer:** Extrae endpoints, métodos HTTP, parámetros, esquemas, validaciones y requisitos de seguridad de contratos OpenAPI.
2. **Architecture Vision Analyzer:** Analiza diagramas de arquitectura mediante un modelo de inteligencia artificial con capacidades de visión.
3. **Contract–Architecture Correlator:** Identifica posibles relaciones entre las operaciones de la API y los componentes de la arquitectura.
4. **Test Case Generator:** Genera casos de prueba estructurados a partir del análisis del contrato y la arquitectura.
5. **Coverage & Traceability Engine:** Evalúa la cobertura del diseño de pruebas y establece trazabilidad entre las operaciones de la API y los casos de prueba.
6. **Report Generator:** Genera informes consolidados de QA en formatos JSON y Markdown.

## Arquitectura

```text
Contrato OpenAPI ─────────┐
                          │
Diagrama de arquitectura ─┤
                          ▼
                   QA Orchestrator
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
     OpenAPI Analyzer       Architecture Vision
                                  Analyzer
            │                           │
            └─────────────┬─────────────┘
                          ▼
              Contract–Architecture
                    Correlator
                          │
                          ▼
                Test Case Generator
                          │
                          ▼
             Coverage & Traceability
                      Engine
                          │
                          ▼
                 Report Generator
                          │
                          ▼
                     Artifacts
```

## Requisitos previos

- Python 3.11 o superior.
- [Ollama](https://ollama.com/).
- Git.

El proyecto utiliza el modelo `qwen2.5vl:3b` para el análisis de imágenes de arquitectura y la generación asistida de casos de prueba.

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/alonso0929/ai-api-test-designer.git
cd ai-api-test-designer
```

### 2. Crear el entorno virtual

**Windows PowerShell:**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Instalar las dependencias

```bash
pip install -r requirements.txt
```

### 4. Instalar y configurar Ollama

Descargar e instalar Ollama desde:

https://ollama.com/download

Descargar el modelo requerido:

```bash
ollama pull qwen2.5vl:3b
```

Asegurarse de que Ollama esté ejecutándose antes de iniciar el procesamiento.

## Ejecución del flujo completo

Ejecutar el QA Orchestrator desde la raíz del proyecto:

```bash
python -m ai_api_test_designer.orchestrator.qa_orchestrator --openapi-file samples/sample_openapi.yaml --architecture-image samples/architecture.png --output-dir artifacts --model qwen2.5vl:3b
```

El orquestador ejecuta secuencialmente los seis módulos y genera los archivos correspondientes.

## Archivos generados

La ejecución genera los siguientes archivos:

```text
artifacts/
├── openapi_analysis.json
├── architecture_analysis.json
├── correlation_analysis.json
├── test_cases.json
├── coverage_report.json
├── test_design_report.json
├── test_design_report.md
└── orchestration_manifest.json
```

Estos archivos contienen los resultados de los análisis intermedios, los casos de prueba generados, la información de cobertura y trazabilidad, y el informe consolidado de QA.

## Ejecución individual de módulos

El OpenAPI Analyzer también puede ejecutarse de manera independiente:

```bash
python -m ai_api_test_designer.analyzers.openapi_analyzer samples/sample_openapi.yaml --output openapi_analysis.json
```

## Ejecución de pruebas unitarias

Para ejecutar las pruebas unitarias del proyecto:

```bash
python -m unittest discover -s tests -v
```

## Archivos de entrada

Los archivos de ejemplo se encuentran en el directorio `samples/`:

| Archivo | Descripción |
|---|---|
| `sample_openapi.yaml` | Contrato de ejemplo basado en OpenAPI 3.x. |
| `architecture.png` | Diagrama de arquitectura de software de ejemplo. |

Estos archivos pueden reemplazarse por contratos OpenAPI y diagramas de arquitectura propios.

## Consideraciones importantes

- El OpenAPI Analyzer realiza un análisis estructural determinístico.
- El análisis de arquitectura y la generación de casos de prueba utilizan el modelo configurado en Ollama.
- Las relaciones identificadas entre la API y la arquitectura son correlaciones potenciales que requieren validación.
- Los casos de prueba generados son artefactos de diseño y deben ser revisados por un ingeniero de QA.
- La cobertura representa la cobertura del diseño de pruebas, no la cobertura de pruebas ejecutadas.
- La solución genera diseños de prueba; no ejecuta los casos de prueba generados.
- Las reglas de negocio que no estén expresadas en los artefactos de entrada pueden requerir información adicional y validación humana.

## Alcance del proyecto

AI API Test Designer busca asistir a los ingenieros de QA en el diseño de pruebas de API mediante la combinación de análisis de contratos, comprensión de arquitecturas de software, inteligencia artificial generativa y trazabilidad.

La solución funciona como un asistente inteligente para el diseño de pruebas, no como un framework de ejecución automatizada.