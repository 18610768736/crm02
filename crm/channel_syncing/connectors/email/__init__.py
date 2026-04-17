from __future__ import annotations

from typing import Any

from crm.channel_syncing.connectors.http import pull_via_http, validate_via_http


def get_connector_meta() -> dict[str, object]:
	return {
		"name": "email",
		"label": "Email",
		"direction": ["pull"],
		"status": "baseline",
		"supported_events": ["message.created", "message.replied"],
	}


def normalize_inbound_payload(payload: dict[str, object]) -> dict[str, object]:
	subject = payload.get("subject")
	body = payload.get("body") or payload.get("text")
	normalized = dict(payload)
	normalized.update(
		{
		"event_id": payload.get("event_id") or payload.get("message_id"),
		"conversation_id": payload.get("conversation_id") or payload.get("thread_id"),
		"event_type": payload.get("event_type") or "message.created",
		"event_time": payload.get("event_time") or payload.get("sent_at"),
		"text": body,
		"summary": payload.get("summary") or subject or body,
		"customer_name": payload.get("customer_name") or payload.get("from_name"),
		"owner_name": payload.get("owner_name") or payload.get("mailbox_owner"),
		"external_user_id": payload.get("external_user_id") or payload.get("from_email"),
		"email": payload.get("email") or payload.get("from_email"),
		"reference_doctype": payload.get("reference_doctype"),
		"reference_name": payload.get("reference_name"),
		"workspace_key": payload.get("workspace_key") or payload.get("mailbox_id"),
		"workspace_name": payload.get("workspace_name") or payload.get("mailbox_name"),
		"tenant_id": payload.get("tenant_id"),
		"account_id": payload.get("account_id") or payload.get("mailbox_id"),
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
			"email",
			credential,
			cursor=cursor,
			limit=limit,
			default_event_paths=["data.messages", "data.items", "messages"],
		)
	if metadata.get("force_pull_error"):
		raise RuntimeError("email pull failed by test flag")

	sequence = _as_int((cursor or {}).get("cursor_value"), default=0)
	next_sequence = sequence + max(1, min(limit, 1))
	credential_key = credential.get("credential_key") or credential.get("name") or "default"
	workspace_key = metadata.get("workspace_key") or f"email::{credential_key}"
	cursor_key = (cursor or {}).get("cursor_key") or f"email::{credential_key}"
	message_id = f"email-pull-{credential_key}-{next_sequence}"

	event = {
		"event_id": message_id,
		"message_id": message_id,
		"thread_id": f"email-thread-{credential_key}",
		"event_type": metadata.get("event_type") or "message.created",
		"sent_at": metadata.get("sent_at") or f"2026-04-17 12:00:{next_sequence:02d}",
		"subject": metadata.get("subject") or "邮件咨询产品报价",
		"body": metadata.get("body") or "客户通过邮箱咨询报价和交付周期。",
		"summary": metadata.get("summary") or "客户通过邮箱咨询报价",
		"from_email": metadata.get("from_email") or f"buyer-{credential_key}@example.com",
		"customer_name": metadata.get("customer_name") or "邮箱客户",
		"owner_name": metadata.get("owner_name") or "邮箱销售",
		"reference_doctype": metadata.get("reference_doctype"),
		"reference_name": metadata.get("reference_name"),
		"workspace_key": workspace_key,
		"workspace_name": metadata.get("workspace_name") or workspace_key,
		"tenant_id": metadata.get("tenant_id"),
		"account_id": metadata.get("account_id"),
		"cursor_key": cursor_key,
		"cursor_value": str(next_sequence),
	}

	return {
		"events": [event],
		"cursor_key": cursor_key,
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
			"email",
			credential,
			limit=limit,
			default_event_paths=["data.messages", "data.items", "messages"],
		)
	if not credential.get("access_token") and not credential.get("refresh_token"):
		raise ValueError("Missing credential secret for email connector.")
	return {
		"ok": True,
		"channel": "email",
		"mode": "mock",
		"status": "connected",
		"event_count": 0,
		"message": "Mock email connector validation succeeded.",
	}
