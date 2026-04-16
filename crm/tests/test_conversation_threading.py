from frappe.tests import UnitTestCase

from crm.api.channel_sync import (
	get_conversation_thread_detail,
	get_meeting_artifact_detail,
	get_touchpoint_detail,
	ingest_event,
	list_conversation_threads,
)


class TestConversationThreading(UnitTestCase):
	def test_ingest_reuses_existing_thread_for_same_thread_key(self):
		first = ingest_event(
			"qywx",
			{
				"event_id": "evt-thread-001",
				"conversation_id": "conv-thread-001",
				"text": "第一条消息",
				"customer_name": "客户A",
				"reference_doctype": "CRM Lead",
				"reference_name": "LEAD-THREAD-001",
			},
		)
		second = ingest_event(
			"qywx",
			{
				"event_id": "evt-thread-002",
				"conversation_id": "conv-thread-001",
				"text": "第二条消息",
				"customer_name": "客户A",
				"reference_doctype": "CRM Lead",
				"reference_name": "LEAD-THREAD-001",
			},
		)

		self.assertEqual(first["thread_id"], second["thread_id"])

		thread_detail = get_conversation_thread_detail(first["thread_id"])
		self.assertEqual(thread_detail["thread_key"], "conv-thread-001")
		self.assertGreaterEqual(thread_detail["touchpoint_count"], 2)

		touchpoint_detail = get_touchpoint_detail(second["touchpoint_id"])
		self.assertEqual(touchpoint_detail["conversation_thread"], first["thread_id"])

	def test_meeting_artifact_keeps_thread_link(self):
		result = ingest_event(
			"lark",
			{
				"event_id": "evt-thread-003",
				"event_type": "meeting.ended",
				"conversation_id": "conv-thread-003",
				"text": "会议纪要内容",
				"summary": "会议结束",
				"customer_name": "客户B",
				"reference_doctype": "CRM Deal",
				"reference_name": "DEAL-THREAD-003",
				"artifact_type": "Minutes",
				"source_type": "Lark",
				"source_ref": "minutes-thread-003",
			},
		)

		artifact_detail = get_meeting_artifact_detail(result["meeting_artifact_id"])
		self.assertEqual(artifact_detail["conversation_thread"], result["thread_id"])

		thread_list = list_conversation_threads("CRM Deal", "DEAL-THREAD-003")
		self.assertGreaterEqual(thread_list["total_count"], 1)
		self.assertEqual(thread_list["items"][0]["name"], result["thread_id"])

