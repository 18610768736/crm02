import os
from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from crm.api.ai import (
	compile_customer_memory,
	generate_suggestions,
	get_customer_memory,
	get_panel_context,
	get_suggestion_detail,
	list_audit_logs,
	list_customer_memories,
	list_evidence_links,
	list_suggestions,
)
from crm.api.ai_runtime import get_runtime_handshake, get_runtime_status


def _mock_response(status: int, body: str) -> MagicMock:
	response = MagicMock()
	response.status = status
	response.getcode.return_value = status
	response.read.return_value = body.encode("utf-8")
	response.__enter__.return_value = response
	response.__exit__.return_value = False
	return response


class TestAIAPI(UnitTestCase):
	def setUp(self):
		super().setUp()
		self._runtime_env = {
			"OPENCLAW_RUNTIME_MODE": os.getenv("OPENCLAW_RUNTIME_MODE"),
			"OPENCLAW_RUNTIME_URL": os.getenv("OPENCLAW_RUNTIME_URL"),
		}

	def tearDown(self):
		for key, value in self._runtime_env.items():
			if value is None:
				os.environ.pop(key, None)
			else:
				os.environ[key] = value
		super().tearDown()

	def test_get_panel_context_exposes_expected_context_shape(self):
		result = get_panel_context("CRM Lead", "LEAD-0002", "lead_panel")

		self.assertEqual(result["reference"]["doctype"], "CRM Lead")
		self.assertEqual(result["reference"]["name"], "LEAD-0002")
		self.assertEqual(result["context_type"], "lead_panel")
		self.assertGreaterEqual(len(result["actions"]), 3)

	def test_generate_suggestions_uses_prompt_and_returns_stubbed_cards(self):
		result = generate_suggestions(
			"CRM Deal",
			"DEAL-0002",
			channel="email",
			prompt="请起草一封报价跟进邮件",
		)

		self.assertEqual(result["status"], "drafted")
		self.assertEqual(result["agent_request"]["prompt"], "请起草一封报价跟进邮件")
		self.assertEqual(result["runtime"]["status"], "succeeded")
		self.assertEqual(result["suggestions"][0]["channel"], "email")
		self.assertEqual(result["audit"]["action"], "generate_suggestions")
		self.assertTrue(result["audit_id"])
		self.assertGreaterEqual(len(result["evidence_ids"]), 1)

	def test_generate_suggestions_persists_records_for_list_and_detail_apis(self):
		result = generate_suggestions(
			"CRM Deal",
			"DEAL-0003",
			channel="lark",
			prompt="请总结最近一次会议并给出下一步建议",
		)

		self.assertGreaterEqual(len(result["suggestion_ids"]), 2)

		list_payload = list_suggestions("CRM Deal", "DEAL-0003")

		self.assertEqual(list_payload["reference"]["doctype"], "CRM Deal")
		self.assertEqual(list_payload["reference"]["name"], "DEAL-0003")
		self.assertGreaterEqual(list_payload["total_count"], 2)
		self.assertEqual(list_payload["items"][0]["reference"]["name"], "DEAL-0003")
		self.assertEqual(list_payload["items"][0]["status"], "Open")

		detail_payload = get_suggestion_detail(result["suggestion_ids"][0])

		self.assertEqual(detail_payload["reference"]["doctype"], "CRM Deal")
		self.assertEqual(detail_payload["reference"]["name"], "DEAL-0003")
		self.assertEqual(detail_payload["status"], "Open")
		self.assertIn("generated_at", detail_payload)

		audit_payload = list_audit_logs("CRM Deal", "DEAL-0003")
		self.assertGreaterEqual(audit_payload["total_count"], 1)
		self.assertEqual(audit_payload["items"][0]["action"], "generate_suggestions")

		evidence_payload = list_evidence_links("CRM Deal", "DEAL-0003")
		self.assertGreaterEqual(evidence_payload["total_count"], 1)
		self.assertEqual(evidence_payload["items"][0]["reference"]["name"], "DEAL-0003")

	def test_customer_memory_apis_return_compiled_memory(self):
		generate_suggestions(
			"CRM Lead",
			"LEAD-MEMORY-API-001",
			channel="email",
			prompt="总结客户记忆",
		)

		compiled = compile_customer_memory("CRM Lead", "LEAD-MEMORY-API-001")
		self.assertEqual(compiled["reference"]["doctype"], "CRM Lead")
		self.assertTrue(compiled["summary"])

		detail = get_customer_memory("CRM Lead", "LEAD-MEMORY-API-001")
		self.assertEqual(detail["memory_key"], compiled["memory_key"])

		list_payload = list_customer_memories(reference_doctype="CRM Lead")
		self.assertGreaterEqual(list_payload["total_count"], 1)

	def test_runtime_status_api_returns_readiness_payload(self):
		os.environ["OPENCLAW_RUNTIME_MODE"] = "production"
		os.environ["OPENCLAW_RUNTIME_URL"] = "https://runtime.example.com/runs"

		with patch(
			"crm.ai.agent_client.request.urlopen",
			side_effect=[
				_mock_response(200, '{"status":"ok","healthy":true}'),
				_mock_response(
					200,
					'{"status":"ok","protocol_version":"crm-ai-runtime.v1","runtime_version":"2026.04.17","capabilities":["context_grounding","draft_generation","audit_logging"]}',
				),
			],
		):
			result = get_runtime_status()

		self.assertEqual(result["mode"], "production")
		self.assertTrue(result["health"]["healthy"])
		self.assertTrue(result["ready"])
		self.assertTrue(result["handshake"]["compatible"])

	def test_runtime_handshake_api_reports_missing_capabilities(self):
		os.environ["OPENCLAW_RUNTIME_URL"] = "https://runtime.example.com/runs"

		with patch(
			"crm.ai.agent_client.request.urlopen",
			return_value=_mock_response(
				200,
				'{"status":"ok","protocol_version":"crm-ai-runtime.v1","runtime_version":"2026.04.17","capabilities":["context_grounding"]}',
			),
		):
			result = get_runtime_handshake()

		self.assertFalse(result["compatible"])
		self.assertFalse(result["capabilities_ok"])
		self.assertEqual(result["reason"], "missing_capabilities")
		self.assertIn("draft_generation", result["missing_capabilities"])
