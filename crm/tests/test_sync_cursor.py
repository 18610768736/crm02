from frappe.tests import UnitTestCase

from crm.api.channel_sync import (
	get_sync_cursor_detail,
	ingest_event,
	list_channel_workspaces,
	list_sync_cursors,
)


class TestSyncCursor(UnitTestCase):
	def test_ingest_creates_workspace_and_cursor(self):
		result = ingest_event(
			"email",
			{
				"event_id": "evt-cursor-001",
				"workspace_key": "email::inbox-sales",
				"workspace_name": "Sales Inbox",
				"cursor_key": "email::inbox-sales",
				"cursor_value": "cursor-001",
				"text": "首次同步",
			},
		)

		self.assertTrue(result["workspace_id"])
		self.assertTrue(result["cursor_id"])

		cursor = get_sync_cursor_detail(result["cursor_id"])
		self.assertEqual(cursor["cursor_key"], "email::inbox-sales")
		self.assertEqual(cursor["cursor_value"], "cursor-001")
		self.assertEqual(cursor["status"], "Succeeded")

	def test_repeated_ingest_reuses_cursor_key_and_updates_value(self):
		first = ingest_event(
			"email",
			{
				"event_id": "evt-cursor-002a",
				"workspace_key": "email::inbox-support",
				"cursor_key": "email::inbox-support",
				"cursor_value": "cursor-002a",
				"text": "同步A",
			},
		)
		second = ingest_event(
			"email",
			{
				"event_id": "evt-cursor-002b",
				"workspace_key": "email::inbox-support",
				"cursor_key": "email::inbox-support",
				"cursor_value": "cursor-002b",
				"text": "同步B",
			},
		)

		self.assertEqual(first["cursor_id"], second["cursor_id"])
		cursor = get_sync_cursor_detail(second["cursor_id"])
		self.assertEqual(cursor["cursor_value"], "cursor-002b")

	def test_list_sync_cursors_supports_workspace_filter(self):
		result = ingest_event(
			"qywx",
			{
				"event_id": "evt-cursor-003",
				"workspace_key": "qywx::tenant-filter",
				"workspace_name": "Tenant Filter",
				"tenant_id": "tenant-filter",
				"cursor_key": "qywx::tenant-filter",
				"cursor_value": "cursor-003",
				"text": "同步过滤",
			},
		)

		workspaces = list_channel_workspaces(channel="qywx")
		self.assertTrue(any(item["name"] == result["workspace_id"] for item in workspaces["items"]))

		cursors = list_sync_cursors(channel="qywx", workspace_id=result["workspace_id"])
		self.assertTrue(any(item["name"] == result["cursor_id"] for item in cursors["items"]))
