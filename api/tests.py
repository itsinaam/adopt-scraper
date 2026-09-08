from django.test import TestCase, Client


class CorsAndHealthTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_health_check_cors_headers_localhost_5173(self):
        response = self.client.get(
            "/api/health/",
            HTTP_ORIGIN="http://localhost:5173",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")

    def test_cors_preflight_options_request(self):
        response = self.client.options(
            "/api/health/",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")
