from __future__ import annotations

from typing import Any

from crm.channel_syncing.connectors.http import pull_via_http, validate_via_http


def get_connector_meta() -> dict[str, object]:
	return {
		"name": "qywx",
		"label": "WeCom",
		"direction": ["pull", "webhook"],
		"status": "baseline",
		"supported_events": ["message.created", "customer.updated"],
	}


def normalize_inbound_payload(payload: dict[str, object]) -> dict[str, object]:
	normalized = dict(payload)
	normalized.update(
		{
		"event_id": payload.get("event_id") or payload.get("msgid") or payload.get("event_idempotency_key"),
		"conversation_id": payload.get("conversation_id") or payload.get("chat_id"),
		"event_type": payload.get("event_type") or "message.created",
		"event_time": payload.get("event_time") or payload.get("msgtime"),
		"text": payload.get("text") or payload.get("content"),
		"summary": payload.get("summary") or payload.get("text") or payload.get("content"),
		"customer_name": payload.get("customer_name") or payload.get("external_name"),
		"owner_name": payload.get("owner_name") or payload.get("staff_name"),
		"external_user_id": payload.get("external_user_id") or payload.get("external_userid"),
		"phone": payload.get("phone"),
		"email": payload.get("email"),
		"reference_doctype": payload.get("reference_doctype"),
		"reference_name": payload.get("reference_name"),
		"workspace_key": payload.get("workspace_key") or payload.get("corp_id"),
		"workspace_name": payload.get("workspace_name") or payload.get("corp_name"),
		"tenant_id": payload.get("tenant_id") or payload.get("corp_id"),
		"account_id": payload.get("account_id") or payload.get("agent_id"),
		"source_payload": payload,
		}
	)
	return normalized


def _as_int(value: Any, default: int = 0) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def pull_events(
	credential: dict[str, Any],
	cursor: dict[str, Any] | None = None,
	limit: int = 20,
) -> dict[str, Any]:
	metadata = credential.get("metadata") or {}
	if str(metadata.get("pull_mode") or "").strip().lower() == "http":
		return pull_via_http(
			"qywx",
			credential,
			cursor=cursor,
			limit=limit,
			default_event_paths=["data.messages", "data.external_contact_messages"],
		)
	if metadata.get("force_pull_error"):
		raise RuntimeError("qywx pull failed by test flag")

	sequence = _as_int((cursor or {}).get("cursor_value"), default=0)
	next_sequence = sequence + max(1, min(limit, 1))
	credential_key = credential.get("credential_key") or credential.get("name") or "default"
	workspace_key = metadata.get("workspace_key") or f"qywx::{credential_key}"
	event_id = f"qywx-pull-{credential_key}-{next_sequence}"

	event = {
		"event_id": event_id,
		"conversation_id": f"qywx-conv-{credential_key}",
		"event_type": metadata.get("event_type") or "message.created",
		"event_time": metadata.get("event_time") or f"2026-04-17 10:00:{next_sequence:02d}",
		"text": metadata.get("text") or "企业微信客户咨询产品方案",
		"summary": metadata.get("summary") or "企业微信客户咨询产品方案",
		"external_user_id": metadata.get("external_user_id") or f"qywx-user-{credential_key}",
		"customer_name": metadata.get("customer_name") or "企业微信客户",
		"owner_name": metadata.get("owner_name") or "企业微信销售",
		"reference_doctype": metadata.get("reference_doctype"),
		"reference_name": metadata.get("reference_name"),
		"workspace_key": workspace_key,
		"workspace_name": metadata.get("workspace_name") or workspace_key,
		"tenant_id": metadata.get("tenant_id"),
		"account_id": metadata.get("account_id"),
		"cursor_key": (cursor or {}).get("cursor_key") or f"qywx::{credential_key}",
		"cursor_value": str(next_sequence),
	}

	return {
		"events": [event],
		"cursor_key": event["cursor_key"],
		"next_cursor_value": str(next_sequence),
		"status": "ok",
		"has_more": False,
	}


def validate_connection(
	credential: dict[str, Any],
	limit: int = 1,
) -> dict[str, Any]:
	metadata = credential.get("metadata") or {}
	if str(metadata.get("pull_mode") or "").strip().lower() == "http":
		return validate_via_http(
			"qywx",
			credential,
			limit=limit,
			default_event_paths=["data.messages", "data.external_contact_messages"],
		)
	if not credential.get("access_token"):
		raise ValueError("Missing access token for qywx connector.")
	return {
		"ok": True,
		"channel": "qywx",
		"mode": "mock",
		"status": "connected",
		"event_count": 0,
		"message": "Mock qywx connector validation succeeded.",
	}
