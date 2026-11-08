# Informe consolidado de diseño de pruebas

**Contrato:** Payments API **Versión:** 1.0.0
**Generado (UTC):** 2026-11-08T05:24:08.840455+00:00

> Este informe representa análisis y cobertura de diseño. No implica que los casos hayan sido ejecutados.

## 1. Resumen ejecutivo

- Operaciones OpenAPI: **2**
- Casos de prueba diseñados: **21**
- Cobertura de diseño: **94.44%**
- Elementos del contrato cubiertos: **17 / 18**
- Elementos sin cobertura: **1**
- Casos de integración candidatos: **4**

## 2. Contrato OpenAPI

- Título: Payments API
- Versión OpenAPI: 3.0.3
- Validación: válido

| Operación | Método | Ruta | Obsoleta |
|---|---:|---|---|
| createPayment | POST | `/payments` | No |
| getPayment | GET | `/payments/{paymentId}` | No |

## 3. Diseño de casos de prueba

- Casos positivos: 7
- Casos negativos: 8
- Casos de seguridad: 2
- Casos candidatos de integración: 4

| ID | Operación | Categoría | Prioridad | HTTP esperado | Trazabilidad |
|---|---|---|---|---:|---|
| TC-001 | createPayment | positive | medium | 201 | linked_to_contract |
| TC-002 | createPayment | positive | medium | 201 | linked_to_contract |
| TC-003 | createPayment | negative | high | 400 | linked_to_contract |
| TC-004 | createPayment | positive | medium | 201 | linked_to_contract |
| TC-005 | createPayment | negative | high | 400 | linked_to_contract |
| TC-006 | createPayment | positive | medium | 201 | linked_to_contract |
| TC-007 | createPayment | positive | medium | 201 | linked_to_contract |
| TC-008 | createPayment | negative | high | 400 | linked_to_contract |
| TC-009 | createPayment | positive | medium | 201 | linked_to_contract |
| TC-010 | createPayment | negative | high | 400 | linked_to_contract |
| TC-011 | createPayment | negative | high | 400 | linked_to_contract |
| TC-012 | createPayment | negative | high | 400 | linked_to_contract |
| TC-013 | createPayment | security | high | 401 | linked_to_contract |
| TC-014 | createPayment | integration_candidate | medium | No definido | architecture_candidate_requires_review |
| TC-015 | createPayment | integration_candidate | medium | No definido | architecture_candidate_requires_review |
| TC-016 | getPayment | positive | medium | 200 | linked_to_contract |
| TC-017 | getPayment | negative | high | 404 | linked_to_contract |
| TC-018 | getPayment | negative | high | No definido | linked_to_contract |
| TC-019 | getPayment | security | high | No definido | linked_to_contract |
| TC-020 | getPayment | integration_candidate | medium | No definido | architecture_candidate_requires_review |
| TC-021 | getPayment | integration_candidate | medium | No definido | architecture_candidate_requires_review |

## 4. Cobertura por operación

| Operación | Elementos | Cubiertos | Solo candidatos | Sin cobertura | Cobertura | Mapeo arquitectónico |
|---|---:|---:|---:|---:|---:|---|
| createPayment | 12 | 11 | 0 | 1 | 91.67% | candidate_requires_review |
| getPayment | 6 | 6 | 0 | 0 | 100.0% | candidate_requires_review |

### Elementos sin cobertura

- **createPayment:request_property:description**: Request property 'description'

## 5. Correlación con arquitectura

- Componentes detectados: 8
- Conexiones detectadas: 7
- Mapeos confirmados: 0
- Mapeos candidatos: 2

| Endpoint | Servicio candidato | Estado | Revisión requerida |
|---|---|---|---|
| POST /payments | PaymentService | candidate | Sí |
| GET /payments/{paymentId} | PaymentService | candidate | Sí |

- Servicios sin mapeo: AuthService, OrderService
- Componentes arquitectónicos sin mapeo: API-Gateway, User

## 6. Puntos que requieren revisión

- **endpoint_service_mapping — POST /payments**: La asociación se basa en similitud heurística y requiere validación.
- **endpoint_service_mapping — GET /payments/{paymentId}**: La asociación se basa en similitud heurística y requiere validación.
- **service_dependency — AuthService**: La conexión visual no confirma semántica de lectura o escritura.
- **service_dependency — OrderService**: La conexión visual no confirma semántica de lectura o escritura.
- **service_dependency — PaymentService**: La conexión visual no confirma semántica de lectura o escritura.
- **uncovered_contract_element — createPayment:request_property:description**: Request property 'description'

## 7. Supuestos y limitaciones

- Supuesto: Los datos de prueba que requieren registros existentes deben prepararse en el entorno.
- Supuesto: Los códigos HTTP esperados se incluyen únicamente cuando están documentados en OpenAPI.
- El informe consolida resultados de análisis y diseño; no ejecuta pruebas.
- Los mapeos entre endpoints y servicios son candidatos hasta su validación.
- Las relaciones entre servicios y bases de datos no prueban operaciones de lectura o escritura.
- No se infieren reglas de negocio que no estén presentes en los artefactos de entrada.
- La cobertura depende de los elementos extraídos y de la trazabilidad declarada por los casos.

## 8. Conclusiones

- Se analizaron 2 operaciones del contrato.
- Se consolidaron 21 casos de prueba diseñados.
- La cobertura de diseño del contrato es 94.44%; este valor no representa ejecución de pruebas.
- Se identificaron 6 elementos que requieren revisión o atención antes de considerar cerrado el diseño.
