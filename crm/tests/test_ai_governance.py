from frappe.tests import UnitTestCase

from crm.api.ai import generate_suggestions, list_audit_logs, list_evidence_links


class TestAIGovernance(UnitTestCase):
	def test_generate_suggestions_persists_audit_and_evidence_links(self):
		result = generate_suggestions(
			"CRM Lead",
			"LEAD-GOV-0001",
			channel="email",
			prompt="请给出下一步销售建议",
		)

		self.assertTrue(result["audit_id"])
		self.assertGreaterEqual(len(result["evidence_ids"]), 1)

		audit_payload = list_audit_logs("CRM Lead", "LEAD-GOV-0001")
		self.assertGreaterEqual(audit_payload["total_count"], 1)
		self.assertEqual(audit_payload["items"][0]["action"], "generate_suggestions")

		evidence_payload = list_evidence_links("CRM Lead", "LEAD-GOV-0001")
		self.assertGreaterEqual(evidence_payload["total_count"], 1)
		self.assertEqual(evidence_payload["items"][0]["reference"]["name"], "LEAD-GOV-0001")

