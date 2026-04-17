import os
from unittest.mock import MagicMock, patch
from urllib import error as urllib_error

from frappe.tests import UnitTestCase

from crm.ai.agent_client import check_runtime_health, execute_agent_request
from crm.api.ai_runtime import run_runtime_smoke_test


def _mock_response(status: int, body: str) -> MagicMock:
	response = MagicMock()
	response.status = status
	response.getcode.return_value = status
	response.read.return_value = body.encode("utf-8")
	response.__enter__.return_value = response
	response.__exit__.return_value = False
	return response


class TestAIRuntimeIntegration(UnitTestCase):
	def setUp(self):
		super().setUp()
		self._env_backup = {
			"OPENCLAW_RUNTIME_REQUIRED": os.getenv("OPENCLAW_RUNTIME_REQUIRED"),
			"OPENCLAW_RUNTIME_URL": os.getenv("OPENCLAW_RUNTIME_URL"),
			"OPENCLAW_RUNTIME_HEALTH_URL": os.getenv("OPENCLAW_RUNTIME_HEALTH_URL"),
			"OPENCLAW_RUNTIME_ALLOW_SIMULATION_FALLBACK": os.getenv(
				"OPENCLAW_RUNTIME_ALLOW_SIMULATION_FALLBACK"
			),
		}

	def tearDown(self):
		for key, value in self._env_backup.items():
			if value is None:
				os.environ.pop(key, None)
			else:
				os.environ[key] = value
		super().tearDown()

	def test_required_mode_fails_when_runtime_url_missing(self):
		os.environ["OPENCLAW_RUNTIME_REQUIRED"] = "1"
		os.environ.pop("OPENCLAW_RUNTIME_URL", None)

		result = execute_agent_request({"provider": "clawx", "mode": "crm_copilot", "prompt": "runtime"})
		self.assertEqual(result["status"], "failed")
		self.assertEqual(result["mode"], "required_runtime_missing")
		self.assertEqual(result["error"]["type"], "RuntimeConfigurationError")

	def test_check_runtime_health_reports_healthy_runtime(self):
		os.environ["OPENCLAW_RUNTIME_URL"] = "https://runtime.example.com/runs"
		os.environ["OPENCLAW_RUNTIME_REQUIRED"] = "1"

		with patch(
			"crm.ai.agent_client.request.urlopen",
			return_value=_mock_response(200, '{"status":"ok","healthy":true}'),
		):
			health = check_runtime_health()

		self.assertTrue(health["configured"])
		self.assertTrue(health["healthy"])
		self.assertEqual(health["reason"], "ok")
		self.assertEqual(health["mode"], "openclaw_http")
		self.assertEqual(health["health_url"], "https://runtime.example.com/health")

	def test_check_runtime_health_keeps_path_prefix_when_deriving_health_url(self):
		os.environ["OPENCLAW_RUNTIME_URL"] = "https://runtime.example.com/openclaw/runs"

		with patch(
			"crm.ai.agent_client.request.urlopen",
			return_value=_mock_response(200, '{"status":"ok","healthy":true}'),
		):
			health = check_runtime_health()

		self.assertEqual(health["health_url"], "https://runtime.example.com/openclaw/health")

	def test_run_runtime_smoke_test_uses_http_runtime(self):
		os.environ["OPENCLAW_RUNTIME_URL"] = "https://runtime.example.com/runs"
		os.environ["OPENCLAW_RUNTIME_REQUIRED"] = "1"
		os.environ["OPENCLAW_RUNTIME_ALLOW_SIMULATION_FALLBACK"] = "0"

		runtime_response = _mock_response(
			200,
			'{"run_id":"run-real-001","status":"succeeded","result":{"summary":"runtime ok"}}',
		)
		health_response = _mock_response(200, '{"status":"ok","healthy":true}')
		with patch(
			"crm.ai.agent_client.request.urlopen",
			side_effect=[runtime_response, health_response],
		):
			result = run_runtime_smoke_test("CRM Deal", "DEAL-RUNTIME-001", channel="lark")

		self.assertEqual(result["status"], "succeeded")
		self.assertEqual(result["runtime"]["mode"], "openclaw_http")
		self.assertEqual(result["runtime"]["response"]["run_id"], "run-real-001")
		self.assertTrue(result["health"]["healthy"])

	def test_required_runtime_does_not_fallback_to_simulation_on_http_error(self):
		os.environ["OPENCLAW_RUNTIME_URL"] = "https://runtime.example.com/runs"
		os.environ["OPENCLAW_RUNTIME_REQUIRED"] = "1"
		os.environ["OPENCLAW_RUNTIME_ALLOW_SIMULATION_FALLBACK"] = "1"

		with patch(
			"crm.ai.agent_client.request.urlopen",
			side_effect=urllib_error.URLError("connection refused"),
		):
			result = execute_agent_request(
				{"provider": "clawx", "mode": "crm_copilot", "prompt": "runtime hard fail"},
				max_retries=0,
			)

		self.assertEqual(result["status"], "failed")
		self.assertNotEqual(result.get("mode"), "simulation_fallback")
		self.assertIn("runtime unreachable", result["error"]["message"])
