from frappe.tests import UnitTestCase

from crm.api.ai import generate_suggestions, list_audit_logs, list_evidence_links


class TestAIGovernance(UnitTestCase):
	def _run_generate(self, reference_doctype: str, reference_name: str) -> dict:
		return generate_suggestions(
			reference_doctype,
			reference_name,
			channel="email",
			prompt="请给出下一步销售建议",
		)

	def test_generate_suggestions_persists_audit_log(self):
		result = self._run_generate("CRM Lead", "LEAD-GOV-AUD-0001")

		self.assertTrue(result["audit_id"])
		audit_payload = list_audit_logs("CRM Lead", "LEAD-GOV-AUD-0001")
		self.assertGreaterEqual(audit_payload["total_count"], 1)
		self.assertEqual(audit_payload["items"][0]["action"], "generate_suggestions")
		self.assertEqual(audit_payload["items"][0]["name"], result["audit_id"])

	def test_generate_suggestions_persists_evidence_links(self):
		result = self._run_generate("CRM Lead", "LEAD-GOV-EVD-0001")
		self.assertGreaterEqual(len(result["evidence_ids"]), 1)

		evidence_payload = list_evidence_links("CRM Lead", "LEAD-GOV-EVD-0001")
		self.assertGreaterEqual(evidence_payload["total_count"], 1)
		self.assertIn(evidence_payload["items"][0]["name"], result["evidence_ids"])

	def test_list_audit_logs_by_reference(self):
		self._run_generate("CRM Deal", "DEAL-GOV-0001")
		audit_payload = list_audit_logs("CRM Deal", "DEAL-GOV-0001")
		self.assertEqual(audit_payload["reference"]["doctype"], "CRM Deal")
		self.assertEqual(audit_payload["reference"]["name"], "DEAL-GOV-0001")
		self.assertGreaterEqual(audit_payload["total_count"], 1)

	def test_list_evidence_links_by_reference(self):
		self._run_generate("CRM Deal", "DEAL-GOV-0002")
		evidence_payload = list_evidence_links("CRM Deal", "DEAL-GOV-0002")
		self.assertEqual(evidence_payload["reference"]["doctype"], "CRM Deal")
		self.assertEqual(evidence_payload["reference"]["name"], "DEAL-GOV-0002")
		self.assertGreaterEqual(evidence_payload["total_count"], 1)
		self.assertEqual(evidence_payload["items"][0]["reference"]["name"], "DEAL-GOV-0002")

	def test_governance_fallback_when_reference_missing(self):
		result = self._run_generate("Missing CRM DocType", "MISSING-GOV-0001")
		self.assertTrue(result["audit_id"])
		self.assertGreaterEqual(len(result["evidence_ids"]), 1)

		audit_payload = list_audit_logs("Missing CRM DocType", "MISSING-GOV-0001")
		evidence_payload = list_evidence_links("Missing CRM DocType", "MISSING-GOV-0001")
		self.assertGreaterEqual(audit_payload["total_count"], 1)
		self.assertGreaterEqual(evidence_payload["total_count"], 1)

