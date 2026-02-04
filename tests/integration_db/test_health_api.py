import unittest
from fastapi.testclient import TestClient

from app import app


class TestHealthAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_health_ok(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
