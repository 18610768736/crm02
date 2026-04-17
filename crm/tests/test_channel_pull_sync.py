from frappe.tests import UnitTestCase

from crm.api.channel_sync import (
	get_channel_credential_detail,
	get_sync_cursor_detail,
	list_channel_credentials,
	list_sync_alerts,
	list_sync_cursors,
	run_pull_sync,
	upsert_channel_credential,
)
from crm.channel_syncing.alerts import reset_sync_alerts


class TestChannelPullSync(UnitTestCase):
	def setUp(self):
		super().setUp()
		reset_sync_alerts()

	def tearDown(self):
		reset_sync_alerts()
		super().tearDown()

	def test_channel_credential_crud_contract(self):
		upsert_result = upsert_channel_credential(
			channel="email",
			credential_key="cred-crud-email-001",
			workspace_id=None,
			auth_type="Bearer Token",
			base_url="https://mail.example.com",
			access_token="access-token-crud-001",
			refresh_token="refresh-token-crud-001",
			status="Active",
			metadata={"workspace_key": "email::sales-crud"},
		)
		self.assertTrue(upsert_result["ok"])
		credential_id = upsert_result["credential"]["name"]
		self.assertTrue(upsert_result["credential"]["has_access_token"])
		self.assertNotEqual(upsert_result["credential"]["access_token"], "access-token-crud-001")

		list_payload = list_channel_credentials(channel="email")
		self.assertGreaterEqual(list_payload["total_count"], 1)
		self.assertTrue(any(item["name"] == credential_id for item in list_payload["items"]))

		detail = get_channel_credential_detail(credential_id)
		self.assertNotEqual(detail["access_token"], "access-token-crud-001")
		self.assertNotEqual(detail["refresh_token"], "refresh-token-crud-001")
		self.assertTrue(detail["has_access_token"])
		self.assertTrue(detail["has_refresh_token"])

	def test_run_pull_sync_succeeds_and_updates_cursor(self):
		credential = upsert_channel_credential(
			channel="email",
			credential_key="cred-sync-email-001",
			access_token="access-token-sync-001",
			status="Active",
			metadata={"workspace_key": "email::sync-success"},
		)["credential"]

		result = run_pull_sync(
			channel="email",
			credential_id=credential["name"],
			limit=1,
			max_retries=1,
		)
		self.assertEqual(result["status"], "succeeded")
		self.assertGreaterEqual(result["processed_events"], 1)
		self.assertEqual(len(result["results"]), 1)

		cursor_id = result["results"][0]["cursor_id"]
		cursor = get_sync_cursor_detail(cursor_id)
		self.assertEqual(cursor["status"], "Succeeded")
		self.assertEqual(cursor["metadata"]["mode"], "pull_sync")

	def test_run_pull_sync_failure_emits_alert_and_failed_cursor(self):
		credential = upsert_channel_credential(
			channel="qywx",
			credential_key="cred-sync-qywx-fail-001",
			access_token="access-token-fail-001",
			status="Active",
			metadata={"force_pull_error": True},
		)["credential"]

		result = run_pull_sync(
			channel="qywx",
			credential_id=credential["name"],
			limit=1,
			max_retries=1,
		)
		self.assertEqual(result["status"], "failed")
		self.assertEqual(result["results"][0]["status"], "failed")

		alerts = list_sync_alerts(channel="qywx", severity="error")
		self.assertTrue(
			any(
				item["code"] == "pull_sync_failed"
				and item["context"].get("credential_id") == credential["name"]
				for item in alerts["items"]
			)
		)

		cursors = list_sync_cursors(channel="qywx", status="Failed")
		self.assertTrue(
			any(item["metadata"].get("credential_id") == credential["name"] for item in cursors["items"])
		)

	def test_run_pull_sync_reuses_cursor_key_and_advances_cursor(self):
		credential = upsert_channel_credential(
			channel="lark",
			credential_key="cred-sync-lark-001",
			access_token="access-token-lark-001",
			status="Active",
		)["credential"]

		first = run_pull_sync(
			channel="lark",
			credential_id=credential["name"],
			limit=1,
			max_retries=1,
		)
		second = run_pull_sync(
			channel="lark",
			credential_id=credential["name"],
			limit=1,
			max_retries=1,
		)

		first_item = first["results"][0]
		second_item = second["results"][0]
		self.assertEqual(first_item["status"], "succeeded")
		self.assertEqual(second_item["status"], "succeeded")
		self.assertEqual(first_item["cursor_key"], second_item["cursor_key"])
		self.assertEqual(first_item["cursor_id"], second_item["cursor_id"])
		self.assertGreater(int(second_item["cursor_value"]), int(first_item["cursor_value"]))
