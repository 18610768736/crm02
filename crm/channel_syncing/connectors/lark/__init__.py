from __future__ import annotations

from typing import Any


def get_connector_meta() -> dict[str, object]:
	return {
		"name": "lark",
		"label": "Lark",
		"direction": ["pull", "webhook"],
		"status": "baseline",
		"supported_events": ["message.created", "minutes.generated"],
	}


def normalize_inbound_payload(payload: dict[str, object]) -> dict[str, object]:
	normalized = dict(payload)
	normalized.update(
		{
		"event_id": payload.get("event_id") or payload.get("message_id") or payload.get("minutes_token"),
		"conversation_id": payload.get("conversation_id") or payload.get("chat_id"),
		"event_type": payload.get("event_type") or "message.created",
		"event_time": payload.get("event_time") or payload.get("create_time"),
		"text": payload.get("text") or payload.get("content"),
		"summary": payload.get("summary") or payload.get("topic") or payload.get("text"),
		"customer_name": payload.get("customer_name") or payload.get("contact_name"),
		"owner_name": payload.get("owner_name") or payload.get("host_name"),
		"external_user_id": payload.get("external_user_id") or payload.get("open_id"),
		"email": payload.get("email"),
		"artifact_type": payload.get("artifact_type"),
		"source_type": payload.get("source_type") or "Lark",
		"source_ref": payload.get("source_ref") or payload.get("minutes_token"),
		"reference_doctype": payload.get("reference_doctype"),
		"reference_name": payload.get("reference_name"),
		"workspace_key": payload.get("workspace_key") or payload.get("tenant_key"),
		"workspace_name": payload.get("workspace_name") or payload.get("tenant_name"),
		"tenant_id": payload.get("tenant_id") or payload.get("tenant_key"),
		"account_id": payload.get("account_id") or payload.get("app_id"),
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
	if metadata.get("force_pull_error"):
		raise RuntimeError("lark pull failed by test flag")

	sequence = _as_int((cursor or {}).get("cursor_value"), default=0)
	next_sequence = sequence + max(1, min(limit, 1))
	credential_key = credential.get("credential_key") or credential.get("name") or "default"
	workspace_key = metadata.get("workspace_key") or f"lark::{credential_key}"
	cursor_key = (cursor or {}).get("cursor_key") or f"lark::{credential_key}"
	is_meeting = bool(metadata.get("emit_meeting"))
	event_type = "meeting.ended" if is_meeting else "message.created"
	minutes_token = f"lark-minutes-{credential_key}-{next_sequence}"

	event: dict[str, Any] = {
		"event_id": f"lark-pull-{credential_key}-{next_sequence}",
		"conversation_id": f"lark-conv-{credential_key}",
		"event_type": metadata.get("event_type") or event_type,
		"event_time": metadata.get("event_time") or f"2026-04-17 11:00:{next_sequence:02d}",
		"text": metadata.get("text") or ("飞书会议纪要" if is_meeting else "飞书客户消息"),
		"summary": metadata.get("summary") or ("飞书会议纪要已生成" if is_meeting else "飞书客户消息"),
		"external_user_id": metadata.get("external_user_id") or f"lark-open-{credential_key}",
		"customer_name": metadata.get("customer_name") or "飞书客户",
		"owner_name": metadata.get("owner_name") or "飞书销售",
		"reference_doctype": metadata.get("reference_doctype"),
		"reference_name": metadata.get("reference_name"),
		"workspace_key": workspace_key,
		"workspace_name": metadata.get("workspace_name") or workspace_key,
		"tenant_id": metadata.get("tenant_id"),
		"account_id": metadata.get("account_id"),
		"cursor_key": cursor_key,
		"cursor_value": str(next_sequence),
		"minutes_token": minutes_token,
	}
	if is_meeting:
		event.update(
			{
				"artifact_type": "Minutes",
				"source_type": "Lark",
				"source_ref": minutes_token,
				"action_items": metadata.get("action_items")
				or [{"title": "跟进飞书会议结论", "priority": "Medium"}],
			}
		)

	return {
		"events": [event],
		"cursor_key": cursor_key,
		"next_cursor_value": str(next_sequence),
		"status": "ok",
		"has_more": False,
	}
