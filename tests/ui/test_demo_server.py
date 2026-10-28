"""No-provider tests for the local native-DSH presentation server."""
from __future__ import annotations

import http.client
import importlib.util
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "demo_server", Path(__file__).resolve().parents[2] / "scripts" / "serve_workspace_demo.py"
)
assert SPEC and SPEC.loader
DEMO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEMO)


class DemoServerTests(unittest.TestCase):
    def setUp(self):
        self.server = DEMO.DemoServer(0, "http://127.0.0.1:3081/?token=" + "x" * 32)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, headers=None, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        try:
            conn.request(method, path, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.getheaders(), response.read()
        finally:
            conn.close()

    def cookie(self):
        return {"Cookie": f"{DEMO.DEMO_COOKIE}={self.server.session}"}

    def test_authentication_and_cookie_exchange(self):
        self.assertEqual(self.request("/workspace")[0], 401)
        self.assertEqual(self.request("/start/wrong")[0], 401)
        fake = "dsh-auth-demo=v1.fake; Path=/; HttpOnly; SameSite=Strict"
        with patch.object(DEMO, "exchange_launch_cookie", return_value=fake):
            status, headers, _ = self.request("/start/" + self.server.bootstrap)
        self.assertEqual(status, 303)
        self.assertEqual(dict(headers)["Location"], "http://127.0.0.1:3081/")
        cookies = [value for name, value in headers if name.lower() == "set-cookie"]
        self.assertEqual(len(cookies), 2)
        self.assertTrue(all("HttpOnly" in value and "SameSite=Strict" in value for value in cookies))
        status, headers, body = self.request("/workspace", self.cookie())
        self.assertEqual(status, 303)
        self.assertEqual(dict(headers)["Location"], "http://127.0.0.1:3081/")
        self.assertNotIn(self.server.bootstrap.encode(), body)
        self.assertNotIn(self.server.session.encode(), body)
        self.assertNotIn(b"?token=", body)

    def test_cross_site_and_dns_rebinding_requests_are_rejected(self):
        malicious = (
            {"Host": "evil.example"},
            {"Origin": "https://evil.example"},
            {"Sec-Fetch-Site": "cross-site"},
        )
        for headers in malicious:
            self.assertEqual(self.request("/workspace", {**self.cookie(), **headers})[0], 403)
        cross_site = {"Sec-Fetch-Site": "cross-site"}
        start = "/start/" + self.server.bootstrap
        self.assertEqual(self.request(start, cross_site)[0], 403)

    def test_no_arbitrary_files_api_proxy_or_expired_access(self):
        for path in ("/../AGENTS.md", "/api/session/create", "/runtime/package.json", "/.credentials.yaml"):
            self.assertEqual(self.request(path, self.cookie())[0], 404)
        self.assertEqual(self.request("/workspace?token=secret", self.cookie())[0], 400)
        self.assertEqual(self.request("/workspace", self.cookie(), "POST")[0], 405)
        self.server.expires_at = 0
        self.assertEqual(self.request("/workspace", self.cookie())[0], 401)

    def test_failed_native_auth_stays_closed(self):
        with patch.object(DEMO, "exchange_launch_cookie", side_effect=RuntimeError("secret")):
            status, headers, body = self.request("/start/" + self.server.bootstrap)
        self.assertEqual(status, 503)
        self.assertFalse(any(key.lower() == "set-cookie" for key, _ in headers))
        self.assertNotIn(b"secret", body)

    def test_environment_does_not_inherit_model_or_device_credentials(self):
        inherited = {"DEEPSEEK_API_KEY": "secret", "COMPANY_AGENT_DEVICE_TOKEN": "secret",
                     "COMPANY_AGENT_PRESET": "lab", "NODE_OPTIONS": "untrusted"}
        with patch.dict(DEMO.os.environ, inherited):
            env = DEMO.runtime_environment(Path("/tmp/dsh-demo-home"))
        self.assertEqual(env["COMPANY_AGENT_PRESET"], "boot")
        self.assertEqual(env["COMPANY_AGENT_PROFILE"], "company-agent-minimal")
        for key in ("DEEPSEEK_API_KEY", "COMPANY_AGENT_DEVICE_TOKEN", "NODE_OPTIONS"):
            self.assertNotIn(key, env)


if __name__ == "__main__":
    unittest.main()
