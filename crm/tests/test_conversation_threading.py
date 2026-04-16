from frappe.tests import UnitTestCase

from crm.api.channel_sync import (
	get_conversation_thread_detail,
	get_meeting_artifact_detail,
	get_touchpoint_detail,
	ingest_event,
	list_conversation_threads,
)


class TestConversationThreading(UnitTestCase):
	def _ingest(
		self,
		event_id: str,
		conversation_id: str,
		reference_doctype: str = "CRM Lead",
		reference_name: str = "LEAD-THREAD-BASE",
		channel: str = "qywx",
		extra_payload: dict | None = None,
	) -> dict:
		payload = {
			"event_id": event_id,
			"conversation_id": conversation_id,
			"text": f"message {event_id}",
			"customer_name": "客户线程",
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
		}
		if extra_payload:
			payload.update(extra_payload)
		return ingest_event(channel, payload)

	def test_ingest_creates_thread_on_first_event(self):
		result = self._ingest(
			"evt-thread-create-001",
			"conv-thread-create-001",
			reference_name="LEAD-THREAD-CREATE-001",
		)
		self.assertTrue(result["thread_id"])

		thread_detail = get_conversation_thread_detail(result["thread_id"])
		self.assertEqual(thread_detail["thread_key"], "conv-thread-create-001")
		self.assertEqual(thread_detail["touchpoint_count"], 1)

	def test_ingest_reuses_existing_thread_for_same_thread_key(self):
		first = self._ingest(
			"evt-thread-reuse-001",
			"conv-thread-reuse-001",
			reference_name="LEAD-THREAD-REUSE-001",
		)
		second = self._ingest(
			"evt-thread-reuse-002",
			"conv-thread-reuse-001",
			reference_name="LEAD-THREAD-REUSE-001",
		)
		self.assertEqual(first["thread_id"], second["thread_id"])

	def test_touchpoint_links_to_thread(self):
		result = self._ingest(
			"evt-thread-touchpoint-001",
			"conv-thread-touchpoint-001",
			reference_name="LEAD-THREAD-TOUCH-001",
		)
		touchpoint = get_touchpoint_detail(result["touchpoint_id"])
		self.assertEqual(touchpoint["conversation_thread"], result["thread_id"])

	def test_meeting_artifact_links_to_thread_when_meeting_event(self):
		result = self._ingest(
			"evt-thread-meeting-001",
			"conv-thread-meeting-001",
			reference_doctype="CRM Deal",
			reference_name="DEAL-THREAD-MEETING-001",
			channel="lark",
			extra_payload={
				"event_type": "meeting.ended",
				"artifact_type": "Minutes",
				"source_type": "Lark",
				"source_ref": "minutes-thread-meeting-001",
			},
		)

		artifact = get_meeting_artifact_detail(result["meeting_artifact_id"])
		self.assertEqual(artifact["conversation_thread"], result["thread_id"])

	def test_thread_rollup_updates_last_touchpoint_and_count(self):
		first = self._ingest(
			"evt-thread-rollup-001",
			"conv-thread-rollup-001",
			reference_name="LEAD-THREAD-ROLLUP-001",
			extra_payload={"occurred_at": "2026-04-17T10:00:00+08:00"},
		)
		self._ingest(
			"evt-thread-rollup-002",
			"conv-thread-rollup-001",
			reference_name="LEAD-THREAD-ROLLUP-001",
			extra_payload={"occurred_at": "2026-04-17T10:30:00+08:00"},
		)

		thread = get_conversation_thread_detail(first["thread_id"])
		self.assertGreaterEqual(thread["touchpoint_count"], 2)
		self.assertTrue(thread["last_touchpoint_at"])

	def test_explicit_reference_hint_binds_thread_reference(self):
		result = self._ingest(
			"evt-thread-reference-001",
			"conv-thread-reference-001",
			reference_doctype="CRM Deal",
			reference_name="DEAL-THREAD-REF-001",
		)

		thread_detail = get_conversation_thread_detail(result["thread_id"])
		self.assertEqual(thread_detail["reference"]["doctype"], "CRM Deal")
		self.assertEqual(thread_detail["reference"]["name"], "DEAL-THREAD-REF-001")

		thread_list = list_conversation_threads("CRM Deal", "DEAL-THREAD-REF-001")
		self.assertGreaterEqual(thread_list["total_count"], 1)

	def test_thread_status_updates_when_closed_event_arrives(self):
		first = self._ingest(
			"evt-thread-status-001",
			"conv-thread-status-001",
			reference_name="LEAD-THREAD-STATUS-001",
		)
		closed = self._ingest(
			"evt-thread-status-002",
			"conv-thread-status-001",
			reference_name="LEAD-THREAD-STATUS-001",
			extra_payload={"event_type": "conversation.closed"},
		)

		self.assertEqual(first["thread_id"], closed["thread_id"])
		thread = get_conversation_thread_detail(closed["thread_id"])
		self.assertEqual(thread["status"], "Closed")
