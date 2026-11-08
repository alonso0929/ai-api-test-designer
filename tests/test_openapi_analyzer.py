import unittest
from ai_api_test_designer.analyzers.openapi_analyzer import OpenAPIAnalyzer, OpenAPIAnalysisError

SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Payments API", "version": "1.0"},
    "paths": {
        "/payments/{id}": {
            "parameters": [
                {"name": "id", "in": "path", "required": True,
                 "schema": {"type": "string", "format": "uuid"}}
            ],
            "get": {
                "operationId": "getPayment",
                "security": [{"Bearer": []}],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Payment"}
                            }
                        }
                    },
                    "404": {"description": "Missing"}
                }
            }
        }
    },
    "components": {
        "schemas": {
            "Payment": {
                "type": "object",
                "required": ["id", "amount"],
                "properties": {
                    "id": {"type": "string"},
                    "amount": {"type": "number", "minimum": 0}
                }
            }
        }
    }
}

class AnalyzerTests(unittest.TestCase):
    def test_endpoint_inventory(self):
        result = OpenAPIAnalyzer().analyze_document(SPEC)
        self.assertEqual(result["inventory"]["endpoint_count"], 1)
        self.assertEqual(result["operations"][0]["method"], "GET")
        self.assertEqual(result["operations"][0]["parameters"][0]["name"], "id")

    def test_local_schema_reference(self):
        result = OpenAPIAnalyzer().analyze_document(SPEC)
        schema = result["operations"][0]["responses"][0]["content"][0]["schema"]
        self.assertEqual(schema["required_fields"], ["amount", "id"])

    def test_rejects_openapi_2(self):
        with self.assertRaises(OpenAPIAnalysisError):
            OpenAPIAnalyzer().analyze_document({"swagger": "2.0", "paths": {}})

if __name__ == "__main__":
    unittest.main()
