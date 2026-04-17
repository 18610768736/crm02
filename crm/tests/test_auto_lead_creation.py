from frappe.tests import UnitTestCase

from crm.ai.lead_agent import extract_profile_from_event
from crm.api.channel_sync import ingest_event


class TestAutoLeadCreation(UnitTestCase):
	def test_ingest_autocreates_reference_when_missing(self):
		result = ingest_event(
			"email",
			{
				"event_id": "evt-auto-lead-001",
				"thread_id": "thread-auto-lead-001",
				"subject": "咨询产品定价",
				"body": "我们想了解标准版和企业版报价。",
				"from_email": "autolead001@example.com",
				"customer_name": "自动建档客户A",
			},
		)

		self.assertTrue(result["ok"])
		self.assertEqual(result["match"]["reference"]["doctype"], "CRM Lead")
		self.assertIn(
			result["match"]["strategy"],
			("auto_profile_creation", "external_identity_lookup"),
		)
		if result["auto_profile"]:
			self.assertEqual(
				result["auto_profile"]["reference"]["name"],
				result["match"]["reference"]["name"],
			)
		else:
			self.assertEqual(result["match"]["strategy"], "external_identity_lookup")

	def test_ingest_followup_reuses_autocreated_reference(self):
		first = ingest_event(
			"email",
			{
				"event_id": "evt-auto-lead-002a",
				"thread_id": "thread-auto-lead-002",
				"subject": "首次接触",
				"body": "请发产品资料。",
				"from_email": "autolead002@example.com",
				"customer_name": "自动建档客户B",
			},
		)
		second = ingest_event(
			"email",
			{
				"event_id": "evt-auto-lead-002b",
				"thread_id": "thread-auto-lead-002",
				"subject": "继续沟通",
				"body": "我们希望下周演示。",
				"from_email": "autolead002@example.com",
				"customer_name": "自动建档客户B",
			},
		)

		self.assertEqual(first["match"]["reference"]["doctype"], "CRM Lead")
		self.assertEqual(second["match"]["reference"]["doctype"], "CRM Lead")
		self.assertEqual(
			second["match"]["reference"]["name"],
			first["match"]["reference"]["name"],
		)

	def test_extract_profile_does_not_use_owner_as_organization(self):
		profile = extract_profile_from_event(
			{
				"channel": "email",
				"external_id": "evt-auto-lead-org-001",
				"contact_hints": {
					"display_names": ["客户C"],
					"emails": ["autolead003@example.com"],
					"phone_numbers": [],
					"external_user_ids": [],
				},
				"participants": [
					{"role": "customer", "label": "客户C"},
					{"role": "owner", "label": "销售负责人"},
				],
				"source_payload": {
					"owner_name": "销售负责人",
					"customer_name": "客户C",
				},
			}
		)
		self.assertIsNone(profile["organization"])
