import json
import os
import time

from frappe.tests import UnitTestCase

from crm.api.channel_sync import ingest_event, list_sync_alerts, list_sync_cursors
from crm.channel_syncing.alerts import reset_sync_alerts
from crm.channel_syncing.security import build_webhook_signature, reset_webhook_security_state


class TestChannelSecurity(UnitTestCase):
	def setUp(self):
		super().setUp()
		self._env_backup = {
			"CRM_CHANNEL_SYNC_SECRET_QYWX": os.getenv("CRM_CHANNEL_SYNC_SECRET_QYWX"),
			"CRM_CHANNEL_SYNC_ENFORCE_SIGNATURE_QYWX": os.getenv(
				"CRM_CHANNEL_SYNC_ENFORCE_SIGNATURE_QYWX"
			),
		}
		os.environ["CRM_CHANNEL_SYNC_SECRET_QYWX"] = "unit-test-qywx-secret"
		os.environ["CRM_CHANNEL_SYNC_ENFORCE_SIGNATURE_QYWX"] = "1"
		reset_webhook_security_state()
		reset_sync_alerts()

	def tearDown(self):
		for key, value in self._env_backup.items():
			if value is None:
				os.environ.pop(key, None)
			else:
				os.environ[key] = value
		reset_webhook_security_state()
		reset_sync_alerts()
		super().tearDown()

	def _signed_payload(self, payload: dict) -> tuple[dict, str, str, str]:
		timestamp = str(int(time.time()))
		nonce = f"nonce-{payload.get('event_id')}"
		raw_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
		digest = build_webhook_signature(
			"unit-test-qywx-secret",
			raw_payload,
			timestamp,
			nonce,
		)
		return payload, f"sha256={digest}", timestamp, nonce

	def test_ingest_event_accepts_valid_signature(self):
		payload, signature, timestamp, nonce = self._signed_payload(
			{
				"event_id": "evt-sig-pass-001",
				"conversation_id": "conv-sig-pass-001",
				"text": "签名通过",
				"workspace_key": "qywx::security-pass",
				"cursor_key": "qywx::security-pass",
			}
		)

		result = ingest_event(
			"qywx",
			payload=payload,
			signature=signature,
			timestamp=timestamp,
			nonce=nonce,
		)

		self.assertTrue(result["ok"])
		self.assertTrue(result["security"]["required"])
		self.assertTrue(result["security"]["verified"])
		self.assertEqual(result["security"]["reason"], "ok")

	def test_ingest_event_rejects_invalid_signature_and_emits_alert(self):
		payload = {
			"event_id": "evt-sig-fail-001",
			"conversation_id": "conv-sig-fail-001",
			"text": "签名失败",
			"workspace_key": "qywx::security-fail",
			"cursor_key": "qywx::security-fail",
		}
		timestamp = str(int(time.time()))
		nonce = "nonce-sig-fail-001"

		with self.assertRaises(Exception):
			ingest_event(
				"qywx",
				payload=payload,
				signature="sha256=invalid-signature",
				timestamp=timestamp,
				nonce=nonce,
			)

		alerts = list_sync_alerts(channel="qywx", severity="error")
		self.assertGreaterEqual(alerts["total_count"], 1)
		self.assertEqual(alerts["items"][0]["code"], "webhook_signature_failed")

		cursors = list_sync_cursors(channel="qywx", status="Failed")
		self.assertTrue(
			any(
				item["metadata"].get("event_id") == "evt-sig-fail-001"
				and item["metadata"].get("verification", {}).get("reason") == "signature_mismatch"
				for item in cursors["items"]
			)
		)

	def test_ingest_event_rejects_replayed_nonce(self):
		payload, signature, timestamp, nonce = self._signed_payload(
			{
				"event_id": "evt-sig-replay-001",
				"conversation_id": "conv-sig-replay-001",
				"text": "防重放测试",
				"workspace_key": "qywx::security-replay",
				"cursor_key": "qywx::security-replay",
			}
		)

		first = ingest_event(
			"qywx",
			payload=payload,
			signature=signature,
			timestamp=timestamp,
			nonce=nonce,
		)
		self.assertTrue(first["ok"])

		with self.assertRaises(Exception):
			ingest_event(
				"qywx",
				payload=payload,
				signature=signature,
				timestamp=timestamp,
				nonce=nonce,
			)

		alerts = list_sync_alerts(channel="qywx", severity="error")
		self.assertTrue(
			any(item["context"].get("reason") == "replay_detected" for item in alerts["items"])
		)

	def test_ingest_event_allows_optional_signature_mode(self):
		os.environ["CRM_CHANNEL_SYNC_ENFORCE_SIGNATURE_QYWX"] = "0"
		result = ingest_event(
			"qywx",
			payload={
				"event_id": "evt-sig-optional-001",
				"text": "非强制模式",
				"workspace_key": "qywx::security-optional",
				"cursor_key": "qywx::security-optional",
			},
			verify_signature=0,
		)
		self.assertTrue(result["ok"])
		self.assertFalse(result["security"]["required"])
		self.assertEqual(result["security"]["reason"], "verification_optional")
