import unittest
from unittest.mock import patch

from fastapi import HTTPException

import coordinator


class CoordinatorHelpersTests(unittest.TestCase):
    def test_extract_reasoning_output_supports_envelope_format(self):
        raw = {"ok": True, "result": "hello"}
        normalized = coordinator._extract_reasoning_output(raw, node_id="nodeA")
        self.assertEqual(normalized["node_id"], "nodeA")
        self.assertEqual(normalized["output"], "hello")
        self.assertEqual(normalized["confidence"], 0.8)

    def test_extract_reasoning_output_supports_legacy_format(self):
        raw = {"node_id": "nodeX", "output": "hi", "confidence": 0.9}
        normalized = coordinator._extract_reasoning_output(raw, node_id="nodeA")
        self.assertEqual(normalized["node_id"], "nodeX")
        self.assertEqual(normalized["output"], "hi")
        self.assertEqual(normalized["confidence"], 0.9)


class CoordinatorQueryTests(unittest.TestCase):
    def test_query_flow_returns_consensus(self):
        def fake_post_json(url, payload):
            if url in {coordinator.REASONING_NODES[0][1], coordinator.REASONING_NODES[1][1]}:
                return {"ok": True, "result": f"[ok] Received: {payload['text']}"}
            if url == coordinator.VERIFY_URL:
                return {"verification_score": 0.85}
            if url == coordinator.ETHICS_URL:
                return {"ethics_score": 0.95}
            if url == coordinator.OBSERVER_URL:
                return {"status": "ok"}
            raise AssertionError(f"Unexpected URL {url}")

        with patch("coordinator._post_json", side_effect=fake_post_json):
            body = coordinator.query(coordinator.QueryRequest(query="merhaba"))

        self.assertIn("final_output", body)
        self.assertGreater(body["final_score"], 0)

    def test_query_rejects_empty_input(self):
        with self.assertRaises(HTTPException) as exc:
            coordinator.query(coordinator.QueryRequest(query="   "))
        self.assertEqual(exc.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
