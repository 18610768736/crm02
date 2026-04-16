from frappe.tests import UnitTestCase

from crm.api.meeting_artifacts import (
	get_meeting_artifact_detail,
	import_meeting_artifact,
	list_meeting_artifacts,
)


class TestMeetingArtifactsAPI(UnitTestCase):
	def test_import_meeting_artifact_creates_touchpoint_and_artifact(self):
		result = import_meeting_artifact(
			"lark",
			{
				"event_id": "meeting-import-001",
				"reference_doctype": "CRM Deal",
				"reference_name": "DEAL-MEET-001",
				"summary": "复盘会议完成",
				"text": "纪要正文",
				"source_ref": "minutes-meeting-import-001",
				"action_items": [{"title": "发送版本计划"}],
			},
		)

		self.assertTrue(result["ok"])
		self.assertTrue(result["meeting_artifact_id"])
		self.assertTrue(result["touchpoint_id"])
		self.assertTrue(result["thread_id"])

		artifact_detail = get_meeting_artifact_detail(result["meeting_artifact_id"])
		self.assertEqual(artifact_detail["reference"]["doctype"], "CRM Deal")
		self.assertEqual(artifact_detail["reference"]["name"], "DEAL-MEET-001")
		self.assertGreaterEqual(len(artifact_detail["action_items"]), 1)

	def test_list_meeting_artifacts_returns_imported_records(self):
		import_meeting_artifact(
			"lark",
			{
				"event_id": "meeting-import-002",
				"reference_doctype": "CRM Lead",
				"reference_name": "LEAD-MEET-002",
				"summary": "线索初次沟通",
				"text": "会议要点",
				"source_ref": "minutes-meeting-import-002",
			},
		)

		payload = list_meeting_artifacts("CRM Lead", "LEAD-MEET-002")
		self.assertGreaterEqual(payload["total_count"], 1)
		self.assertEqual(payload["items"][0]["reference"]["name"], "LEAD-MEET-002")
