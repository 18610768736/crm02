from frappe.tests import UnitTestCase

from crm.api.channel_sync import (
	get_channel_workspace_detail,
	get_conversation_thread_detail,
	get_external_identity_detail,
	get_meeting_artifact_detail,
	get_sync_cursor_detail,
	get_touchpoint_detail,
	ingest_event,
	list_channel_workspaces,
	list_conversation_threads,
	list_external_identities,
	list_meeting_artifacts,
	list_sync_cursors,
	list_touchpoints,
)
from crm.channel_syncing.connectors import normalize_connector_payload
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
		self.assertEqual(result["workspace"]["key"], "qywx::default")
		self.assertEqual(result["cursor"]["key"], "qywx::default")
		self.assertEqual(result["contact_hints"]["external_user_ids"], ["ext-001"])
		self.assertEqual(result["participants"][0]["label"], "张三")

	def test_connector_normalizers_map_channel_specific_payloads(self):
		qywx_payload = normalize_connector_payload(
			"qywx",
			{
				"msgid": "qywx-msg-001",
				"chat_id": "qywx-chat-001",
				"content": "客户咨询定价",
				"external_userid": "qywx-user-001",
			},
		)
		self.assertEqual(qywx_payload["event_id"], "qywx-msg-001")
		self.assertEqual(qywx_payload["conversation_id"], "qywx-chat-001")
		self.assertEqual(qywx_payload["external_user_id"], "qywx-user-001")

		lark_payload = normalize_connector_payload(
			"lark",
			{
				"message_id": "lark-msg-001",
				"chat_id": "lark-chat-001",
				"content": "会议纪要",
				"open_id": "lark-open-001",
			},
		)
		self.assertEqual(lark_payload["event_id"], "lark-msg-001")
		self.assertEqual(lark_payload["conversation_id"], "lark-chat-001")
		self.assertEqual(lark_payload["external_user_id"], "lark-open-001")

		email_payload = normalize_connector_payload(
			"email",
			{
				"message_id": "mail-msg-001",
				"thread_id": "mail-thread-001",
				"subject": "报价咨询",
				"from_email": "buyer@example.com",
			},
		)
		self.assertEqual(email_payload["event_id"], "mail-msg-001")
		self.assertEqual(email_payload["conversation_id"], "mail-thread-001")
		self.assertEqual(email_payload["email"], "buyer@example.com")

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
		self.assertTrue(result["workspace_id"])
		self.assertTrue(result["cursor_id"])
		self.assertEqual(result["match"]["reference"]["doctype"], "CRM Lead")
		self.assertTrue(result["auto_profile"])
		self.assertTrue(result["audit_id"])
		self.assertGreaterEqual(len(result["evidence_ids"]), 1)

	def test_ingest_event_uses_connector_normalization(self):
		result = ingest_event(
			"qywx",
			{
				"msgid": "qywx-msg-ingest-001",
				"chat_id": "qywx-chat-ingest-001",
				"content": "请发送方案",
				"external_userid": "qywx-ext-ingest-001",
				"external_name": "客户连接器",
			},
		)

		self.assertEqual(result["normalized_event"]["external_id"], "qywx-msg-ingest-001")
		self.assertEqual(result["normalized_event"]["thread_key"], "qywx-chat-ingest-001")
		self.assertEqual(
			result["normalized_event"]["contact_hints"]["external_user_ids"],
			["qywx-ext-ingest-001"],
		)

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

		workspace_detail = get_channel_workspace_detail(result["workspace_id"])
		self.assertEqual(workspace_detail["channel"], "qywx")
		self.assertEqual(workspace_detail["workspace_key"], "qywx::default")

		cursor_detail = get_sync_cursor_detail(result["cursor_id"])
		self.assertEqual(cursor_detail["status"], "Succeeded")
		self.assertEqual(cursor_detail["cursor_value"], "evt-003")

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

	def test_channel_workspace_and_cursor_list_apis_support_filters(self):
		payload = {
			"event_id": "evt-005",
			"text": "同步游标测试消息",
			"customer_name": "李四",
			"workspace_key": "qywx::tenant-1",
			"workspace_name": "企业微信租户1",
			"tenant_id": "tenant-1",
			"cursor_key": "qywx::tenant-1",
			"cursor_value": "cursor-005",
		}
		result = ingest_event("qywx", payload)

		workspace_list = list_channel_workspaces(channel="qywx")
		self.assertGreaterEqual(workspace_list["total_count"], 1)
		self.assertTrue(any(item["name"] == result["workspace_id"] for item in workspace_list["items"]))

		cursor_list = list_sync_cursors(channel="qywx", workspace_id=result["workspace_id"])
		self.assertGreaterEqual(cursor_list["total_count"], 1)
		self.assertTrue(any(item["name"] == result["cursor_id"] for item in cursor_list["items"]))

	def test_identity_matching_reuses_external_identity_reference(self):
		seed = ingest_event(
			"qywx",
			{
				"event_id": "evt-identity-seed-001",
				"conversation_id": "conv-identity-seed-001",
				"text": "客户首次咨询",
				"external_user_id": "qywx-ext-identity-001",
				"customer_name": "客户A",
				"reference_doctype": "CRM Lead",
				"reference_name": "LEAD-IDENTITY-001",
			},
		)
		self.assertTrue(seed["identity_id"])

		followup = ingest_event(
			"qywx",
			{
				"event_id": "evt-identity-followup-001",
				"conversation_id": "conv-identity-followup-001",
				"text": "客户继续跟进",
				"external_user_id": "qywx-ext-identity-001",
				"customer_name": "客户A",
			},
		)
		self.assertEqual(followup["match"]["strategy"], "external_identity_lookup")
		self.assertEqual(followup["match"]["reference"]["doctype"], "CRM Lead")
		self.assertEqual(followup["match"]["reference"]["name"], "LEAD-IDENTITY-001")

	def test_sync_all_channels_returns_supported_channel_statuses(self):
		result = sync_all_channels()

		self.assertEqual(len(result), 3)
		self.assertEqual([item["channel"] for item in result], ["qywx", "lark", "email"])
