import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from frappe.tests import UnitTestCase

from crm.api.channel_sync import (
	get_channel_credential_detail,
	get_sync_cursor_detail,
	list_channel_credentials,
	list_sync_alerts,
	list_sync_cursors,
	run_pull_sync,
	test_channel_connection as api_test_channel_connection,
	upsert_channel_credential,
	validate_channel_credential,
)
from crm.channel_syncing.alerts import reset_sync_alerts


class _ChannelSyncHTTPServer:
	def __init__(self, routes: dict[str, dict]):
		self._routes = routes
		self._requests: list[dict] = []
		self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._build_handler())
		self._server.routes = routes
		self._server.requests = self._requests
		self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

	def _build_handler(self):
		class Handler(BaseHTTPRequestHandler):
			def do_GET(self):
				self._handle()

			def do_POST(self):
				self._handle()

			def _handle(self):
				length = int(self.headers.get("Content-Length") or 0)
				body = self.rfile.read(length).decode("utf-8") if length else ""
				self.server.requests.append(
					{
						"path": self.path,
						"headers": {key: value for key, value in self.headers.items()},
						"body": body,
					}
				)
				path = self.path.split("?", 1)[0]
				route = self.server.routes.get(path, {"status": 404, "payload": {"error": "not found"}})
				payload = json.dumps(route.get("payload") or {})
				self.send_response(int(route.get("status") or 200))
				self.send_header("Content-Type", "application/json")
				self.end_headers()
				self.wfile.write(payload.encode("utf-8"))

			def log_message(self, format, *args):  # noqa: A003
				return

		return Handler

	@property
	def base_url(self) -> str:
		host, port = self._server.server_address
		return f"http://{host}:{port}"

	@property
	def requests(self) -> list[dict]:
		return self._requests

	def start(self):
		self._thread.start()
		return self

	def stop(self):
		self._server.shutdown()
		self._server.server_close()
		self._thread.join(timeout=5)


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
		self.assertTrue(
			any(
				item["code"] == "pull_sync_retrying"
				and item["context"].get("credential_id") == credential["name"]
				for item in list_sync_alerts(channel="qywx")["items"]
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

	def test_run_pull_sync_supports_configured_http_mode(self):
		server = _ChannelSyncHTTPServer(
			{
				"/mail/messages": {
					"status": 200,
					"payload": {
						"items": [
							{
								"message_id": "mail-http-001",
								"thread_id": "mail-thread-http-001",
								"subject": "HTTP 报价咨询",
								"body": "客户通过 HTTP 邮件接口咨询报价。",
								"from_email": "buyer-http@example.com",
							}
						],
						"next_cursor": "cursor-http-002",
					},
				}
			}
		).start()
		try:
			credential = upsert_channel_credential(
				channel="email",
				credential_key="cred-sync-email-http-001",
				base_url=server.base_url,
				access_token="http-access-token-001",
				status="Active",
				metadata={
					"pull_mode": "http",
					"pull_path": "/mail/messages",
					"events_path": "items",
					"next_cursor_path": "next_cursor",
					"workspace_key": "email::http-mode",
				},
			)["credential"]

			result = run_pull_sync(
				channel="email",
				credential_id=credential["name"],
				limit=1,
				max_retries=0,
			)
		finally:
			server.stop()

		self.assertEqual(result["status"], "succeeded")
		self.assertEqual(result["results"][0]["connector_mode"], "http")
		self.assertEqual(result["results"][0]["event_ids"], ["mail-http-001"])
		self.assertEqual(server.requests[0]["headers"]["Authorization"], "Bearer http-access-token-001")
		self.assertIn("cursor=0", server.requests[0]["path"])
		self.assertIn("limit=1", server.requests[0]["path"])

		cursor = get_sync_cursor_detail(result["results"][0]["cursor_id"])
		self.assertEqual(cursor["metadata"]["connector_mode"], "http")
		self.assertEqual(cursor["cursor_value"], "cursor-http-002")

	def test_validate_channel_credential_and_connection_test_api(self):
		credential = upsert_channel_credential(
			channel="email",
			credential_key="cred-validate-email-001",
			access_token="validate-access-token-001",
			status="Active",
		)["credential"]

		validation = validate_channel_credential(
			channel="email",
			credential_id=credential["name"],
		)
		connection_test = api_test_channel_connection(
			channel="email",
			credential_id=credential["name"],
		)

		self.assertTrue(validation["ok"])
		self.assertEqual(validation["result"]["mode"], "mock")
		self.assertTrue(connection_test["ok"])
		self.assertNotEqual(validation["credential"]["access_token"], "validate-access-token-001")

		detail = get_channel_credential_detail(credential["name"])
		self.assertEqual(detail["failure_count"], 0)
		self.assertEqual(detail["metadata"]["last_validation_status"], "connected")

	def test_validate_channel_credential_failure_updates_status_and_alerts(self):
		credential = upsert_channel_credential(
			channel="qywx",
			credential_key="cred-validate-qywx-fail-001",
			status="Active",
		)["credential"]

		result = validate_channel_credential(
			channel="qywx",
			credential_id=credential["name"],
		)

		self.assertFalse(result["ok"])
		self.assertEqual(result["credential"]["failure_count"], 1)
		self.assertEqual(result["result"]["status"], "failed")
		self.assertEqual(result["alert"]["code"], "credential_validation_failed")

		detail = get_channel_credential_detail(credential["name"])
		self.assertEqual(detail["metadata"]["last_validation_status"], "failed")
