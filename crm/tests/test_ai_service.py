import os

from frappe.tests import UnitTestCase

from crm.ai.service import build_panel_context, generate_suggestions


class TestAIService(UnitTestCase):
	def setUp(self):
		super().setUp()
		self._runtime_env = {
			"OPENCLAW_RUNTIME_REQUIRED": os.getenv("OPENCLAW_RUNTIME_REQUIRED"),
			"OPENCLAW_RUNTIME_URL": os.getenv("OPENCLAW_RUNTIME_URL"),
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
