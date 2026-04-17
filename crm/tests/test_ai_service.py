import os
from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from crm.ai.service import build_panel_context, generate_suggestions


def _mock_response(status: int, body: str) -> MagicMock:
	response = MagicMock()
	response.status = status
	response.getcode.return_value = status
	response.read.return_value = body.encode("utf-8")
	response.__enter__.return_value = response
	response.__exit__.return_value = False
	return response


class TestAIService(UnitTestCase):
	def setUp(self):
		super().setUp()
		self._runtime_env = {
			"OPENCLAW_RUNTIME_MODE": os.getenv("OPENCLAW_RUNTIME_MODE"),
			"OPENCLAW_RUNTIME_REQUIRED": os.getenv("OPENCLAW_RUNTIME_REQUIRED"),
			"OPENCLAW_RUNTIME_URL": os.getenv("OPENCLAW_RUNTIME_URL"),
			"OPENCLAW_RUNTIME_ALLOW_SIMULATION_FALLBACK": os.getenv(
				"OPENCLAW_RUNTIME_ALLOW_SIMULATION_FALLBACK"
			),
		}

	def tearDown(self):
		for key, value in self._runtime_env.items():
			if value is None:
				os.environ.pop(key, None)
			else:
				os.environ[key] = value
		super().tearDown()

	def test_build_panel_context_returns_minimum_panel_shape(self):
		result = build_panel_context("CRM Deal", "DEAL-0001")

		self.assertEqual(result["reference"]["doctype"], "CRM Deal")
		self.assertEqual(result["reference"]["name"], "DEAL-0001")
		self.assertEqual(result["context_type"], "deal_panel")
		self.assertGreaterEqual(len(result["sections"]), 3)
		self.assertIn("supported_channels", result["metadata"])
		self.assertTrue(result["metadata"]["requires_human_review"])

	def test_generate_suggestions_returns_job_and_approval_payload(self):
		result = generate_suggestions(
			"CRM Lead",
			"LEAD-0001",
			channel="qywx",
			prompt="请生成下一次跟进建议",
		)

		self.assertEqual(result["status"], "drafted")
		self.assertEqual(result["reference"]["doctype"], "CRM Lead")
		self.assertEqual(result["job"]["job_type"], "ai_suggestions")
		self.assertEqual(result["job"]["status"], "queued")
		self.assertEqual(result["agent_request"]["channel"], "qywx")
		self.assertEqual(result["runtime"]["status"], "succeeded")
		self.assertTrue(result["approval"]["required"])
		self.assertGreaterEqual(len(result["suggestions"]), 2)
		self.assertTrue(result["audit_id"])
		self.assertGreaterEqual(len(result["evidence_ids"]), 1)

	def test_generate_suggestions_fails_when_runtime_required_but_unavailable(self):
		os.environ["OPENCLAW_RUNTIME_REQUIRED"] = "1"
		os.environ.pop("OPENCLAW_RUNTIME_URL", None)

		result = generate_suggestions("CRM Lead", "LEAD-RUNTIME-FAIL-001", channel="email")
		self.assertEqual(result["status"], "failed")
		self.assertEqual(result["runtime"]["mode"], "required_runtime_missing")
		self.assertEqual(result["suggestion_ids"], [])

	def test_generate_suggestions_surfaces_production_readiness_failure_details(self):
		os.environ["OPENCLAW_RUNTIME_MODE"] = "production"
		os.environ["OPENCLAW_RUNTIME_URL"] = "https://runtime.example.com/runs"
		os.environ["OPENCLAW_RUNTIME_ALLOW_SIMULATION_FALLBACK"] = "1"

		with patch(
			"crm.ai.agent_client.request.urlopen",
			return_value=_mock_response(
				503,
				'{"status":"starting","healthy":false,"detail":"warming up"}',
			),
		):
			result = generate_suggestions("CRM Lead", "LEAD-PRODUCTION-FAIL-001", channel="email")

		self.assertEqual(result["status"], "failed")
		self.assertEqual(result["runtime"]["error"]["type"], "RuntimeReadinessError")
		self.assertEqual(result["runtime"]["readiness"]["health"]["status_code"], 503)
		self.assertEqual(result["runtime"]["readiness"]["health"]["payload"]["detail"], "warming up")
		self.assertEqual(
			result["audit"]["payload"]["runtime_readiness"]["health"]["payload"]["detail"],
			"warming up",
		)
