from frappe.tests import UnitTestCase

from crm.api.channel_sync import (
	get_conversation_thread_detail,
	get_external_identity_detail,
	get_meeting_artifact_detail,
	get_touchpoint_detail,
	ingest_event,
	list_conversation_threads,
	list_external_identities,
	list_meeting_artifacts,
	list_touchpoints,
)
from crm.channel_syncing.background_sync import sync_all_channels
from crm.channel_syncing.normalizer import normalize_event


class TestChannelSyncing(UnitTestCase):
	def test_normalize_event_maps_payload_into_stable_schema(self):
		payload = {
			"event_id": "evt-001",
			"conversation_id": "conv-001",
			"occurred_at": "2026-04-16T09:30:00+08:00",
			"direction": "inbound",
			"text": "客户想了解报价与交付周期",
			"summary": "客户询问报价",
			"external_user_id": "ext-001",
			"phone": "13800138000",
			"email": "buyer@example.com",
			"customer_name": "张三",
			"owner_name": "销售A",
		}

		result = normalize_event("qywx", payload)

		self.assertEqual(result["channel"], "qywx")
		self.assertEqual(result["external_id"], "evt-001")
		self.assertEqual(result["thread_key"], "conv-001")
		self.assertEqual(result["contact_hints"]["external_user_ids"], ["ext-001"])
		self.assertEqual(result["participants"][0]["label"], "张三")

	def test_ingest_event_returns_normalized_payload_and_stub_job(self):
		payload = {
			"event_id": "evt-002",
			"text": "请发报价单",
			"customer_name": "李总",
		}

		result = ingest_event("email", payload)

		self.assertTrue(result["ok"])
		self.assertEqual(result["status"], "accepted")
		self.assertEqual(result["normalized_event"]["external_id"], "evt-002")
		self.assertEqual(result["job"]["job_type"], "channel_sync_ingest")
		self.assertTrue(result["thread_id"])
		self.assertTrue(result["audit_id"])
		self.assertGreaterEqual(len(result["evidence_ids"]), 1)

	def test_ingest_event_persists_touchpoints_and_external_identities(self):
		payload = {
			"event_id": "evt-003",
			"conversation_id": "conv-003",
			"occurred_at": "2026-04-16T11:00:00+08:00",
			"direction": "inbound",
			"text": "想了解本周能否安排产品演示",
			"summary": "客户询问演示安排",
			"external_user_id": "qywx-ext-003",
			"customer_name": "王总",
			"owner_name": "销售B",
			"reference_doctype": "CRM Lead",
			"reference_name": "LEAD-0003",
		}

		result = ingest_event("qywx", payload)

		self.assertTrue(result["ok"])
		self.assertTrue(result["thread_id"])
		self.assertTrue(result["touchpoint_id"])
		self.assertTrue(result["identity_id"])

		touchpoint_list = list_touchpoints("CRM Lead", "LEAD-0003")
		self.assertGreaterEqual(touchpoint_list["total_count"], 1)
		self.assertEqual(touchpoint_list["items"][0]["external_event_id"], "evt-003")

		touchpoint_detail = get_touchpoint_detail(result["touchpoint_id"])
		self.assertEqual(touchpoint_detail["reference"]["doctype"], "CRM Lead")
		self.assertEqual(touchpoint_detail["reference"]["name"], "LEAD-0003")
		self.assertEqual(touchpoint_detail["conversation_thread"], result["thread_id"])

		identity_list = list_external_identities("CRM Lead", "LEAD-0003")
		self.assertGreaterEqual(identity_list["total_count"], 1)
		self.assertEqual(identity_list["items"][0]["external_id"], "qywx-ext-003")

		identity_detail = get_external_identity_detail(result["identity_id"])
		self.assertEqual(identity_detail["reference"]["doctype"], "CRM Lead")
		self.assertEqual(identity_detail["mapping_status"], "Matched")

		thread_list = list_conversation_threads("CRM Lead", "LEAD-0003")
		self.assertGreaterEqual(thread_list["total_count"], 1)

		thread_detail = get_conversation_thread_detail(result["thread_id"])
		self.assertEqual(thread_detail["reference"]["name"], "LEAD-0003")
		self.assertGreaterEqual(thread_detail["touchpoint_count"], 1)

	def test_ingest_event_persists_meeting_artifacts_for_lark_minutes(self):
		payload = {
			"event_id": "evt-004",
			"event_type": "meeting.ended",
			"conversation_id": "meeting-004",
			"occurred_at": "2026-04-16T14:30:00+08:00",
			"text": "会议纪要原文",
			"summary": "PoC 评审会议完成",
			"customer_name": "赵总",
			"owner_name": "销售C",
			"reference_doctype": "CRM Deal",
			"reference_name": "DEAL-0004",
			"artifact_type": "Minutes",
			"source_type": "Lark",
			"source_ref": "minutes-004",
			"action_items": [{"title": "发送报价单", "owner": "销售C"}],
			"risk_signals": [{"label": "预算审批未完成"}],
		}

		result = ingest_event("lark", payload)

		self.assertTrue(result["meeting_artifact_id"])

		artifact_list = list_meeting_artifacts("CRM Deal", "DEAL-0004")
		self.assertGreaterEqual(artifact_list["total_count"], 1)
		self.assertEqual(artifact_list["items"][0]["artifact_type"], "Minutes")

		artifact_detail = get_meeting_artifact_detail(result["meeting_artifact_id"])
		self.assertEqual(artifact_detail["reference"]["doctype"], "CRM Deal")
		self.assertEqual(artifact_detail["reference"]["name"], "DEAL-0004")
		self.assertEqual(artifact_detail["conversation_thread"], result["thread_id"])
		self.assertGreaterEqual(len(artifact_detail["action_items"]), 1)

	def test_sync_all_channels_returns_supported_channel_statuses(self):
		result = sync_all_channels()

		self.assertEqual(len(result), 3)
		self.assertEqual([item["channel"] for item in result], ["qywx", "lark", "email"])
