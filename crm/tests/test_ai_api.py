from frappe.tests import UnitTestCase

from crm.api.ai import (
	generate_suggestions,
	get_panel_context,
	get_suggestion_detail,
	list_audit_logs,
	list_evidence_links,
	list_suggestions,
)


class TestAIAPI(UnitTestCase):
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
