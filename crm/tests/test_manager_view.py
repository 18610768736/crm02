import frappe
from frappe.tests import UnitTestCase

from crm.api.channel_sync import ingest_event
from crm.api.manager_ai import get_manager_overview
from crm.channel_syncing.alerts import emit_sync_alert, reset_sync_alerts


class TestManagerView(UnitTestCase):
	def setUp(self):
		super().setUp()
		reset_sync_alerts()

	def tearDown(self):
		reset_sync_alerts()
		super().tearDown()

	def test_manager_overview_returns_stale_threads_and_alerts(self):
		ingest_event(
			"email",
			{
				"event_id": "evt-manager-thread-001",
				"thread_id": "thread-manager-001",
				"occurred_at": "2025-01-01 10:00:00",
				"subject": "经理视图线程",
				"body": "这是一个较久未跟进的线程。",
				"from_email": "manager001@example.com",
				"customer_name": "经理视图客户",
			},
		)
		emit_sync_alert(
			channel="email",
			code="manager_test_alert",
			severity="error",
			message="manager view alert seed",
		)

		overview = get_manager_overview(limit=10, stale_days=1)
		self.assertGreaterEqual(overview["summary"]["stale_thread_count"], 1)
		self.assertGreaterEqual(overview["summary"]["sync_alert_count"], 1)
		self.assertGreaterEqual(len(overview["stale_threads"]), 1)
		self.assertGreaterEqual(len(overview["sync_alerts"]), 1)

	def test_manager_overview_includes_high_risk_suggestions(self):
		if not frappe.db.exists("DocType", "AI Suggestion"):
			self.skipTest("AI Suggestion DocType is unavailable")

		doc = frappe.get_doc(
			{
				"doctype": "AI Suggestion",
				"title": "高风险外发建议",
				"suggestion_key": "manager-risk-001",
				"channel": "email",
				"status": "Open",
				"risk_level": "High",
				"content": "建议直接发送最终报价给客户。",
				"reason": "客户已明确采购时间窗口",
			}
		)
		doc.insert(ignore_permissions=True)

		overview = get_manager_overview(limit=10, stale_days=1)
		self.assertGreaterEqual(overview["summary"]["high_risk_suggestion_count"], 1)
		self.assertTrue(
			any(item.get("name") == doc.name for item in overview["high_risk_suggestions"])
		)

