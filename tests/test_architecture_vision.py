import unittest
from ai_api_test_designer.analyzers.architecture_vision import ArchitectureVisionAnalyzer

class ArchitectureVisionTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = ArchitectureVisionAnalyzer(model="test-model")

    def test_normalizes_components_and_connections(self):
        result = self.analyzer._normalize({
            "components": [
                {"id":"gateway","name":"API Gateway","type":"gateway","confidence":0.9},
                {"id":"api","name":"Payment API","type":"api","confidence":0.8}
            ],
            "connections": [{"source":"gateway","target":"api","relationship":"routes_to"}]
        })
        self.assertEqual(len(result["components"]), 2)
        self.assertEqual(len(result["connections"]), 1)

    def test_drops_connection_with_unknown_component(self):
        result = self.analyzer._normalize({
            "components":[{"id":"api","name":"API"}],
            "connections":[{"source":"api","target":"missing"}]
        })
        self.assertEqual(result["connections"], [])
        self.assertTrue(result["warnings"])

    def test_clamps_confidence(self):
        result = self.analyzer._normalize({
            "components":[{"id":"api","name":"API","confidence":1.5}]
        })
        self.assertEqual(result["components"][0]["confidence"], 1.0)

if __name__ == "__main__":
    unittest.main()
