from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list[str]:
	if value is None:
		return []
	if isinstance(value, (list, tuple, set)):
		return [str(item) for item in value if item]
	return [str(value)]


def _as_int(value: Any, default: int = 0) -> int:
	if value is None:
		return default
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def normalize_event(channel: str, payload: dict[str, Any]) -> dict[str, Any]:
	event_id = payload.get("event_id") or payload.get("external_id") or payload.get("message_id")
	event_id = event_id or "pending-external-id"
	summary = payload.get("summary") or payload.get("text") or payload.get("body")
	summary = summary or "Channel event received without a summary."
	text = payload.get("text") or payload.get("body") or summary
	customer_name = payload.get("customer_name") or payload.get("sender_name") or payload.get("contact_name")
	customer_name = customer_name or "unknown_customer"
	owner_name = payload.get("owner_name") or payload.get("staff_name") or payload.get("operator_name")
	owner_name = owner_name or "unassigned_owner"
	workspace_key = (
		payload.get("workspace_key")
		or payload.get("tenant_id")
		or payload.get("channel_account")
		or f"{channel}::default"
	)
	cursor_key = payload.get("cursor_key") or workspace_key
	cursor_value = payload.get("cursor_value") or payload.get("event_time") or event_id

	return {
		"channel": channel,
		"event_type": payload.get("event_type") or "message.created",
		"external_id": event_id,
		"thread_key": payload.get("conversation_id") or payload.get("thread_key") or event_id,
		"occurred_at": payload.get("occurred_at") or payload.get("event_time"),
		"direction": payload.get("direction") or "inbound",
		"content": {
			"summary": summary,
			"text": text,
		},
		"contact_hints": {
			"external_user_ids": _as_list(
				payload.get("external_user_id") or payload.get("external_user_ids")
			),
			"phone_numbers": _as_list(payload.get("phone") or payload.get("phones")),
			"emails": _as_list(payload.get("email") or payload.get("emails")),
			"display_names": _as_list(
				payload.get("customer_name") or payload.get("display_name") or payload.get("contact_name")
			),
		},
		"participants": [
			{"role": "customer", "label": customer_name},
			{"role": "owner", "label": owner_name},
		],
		"workspace": {
			"key": workspace_key,
			"name": payload.get("workspace_name") or payload.get("tenant_name") or workspace_key,
			"tenant_id": payload.get("tenant_id"),
			"account_id": payload.get("account_id") or payload.get("channel_account"),
		},
		"cursor": {
			"key": cursor_key,
			"value": cursor_value,
			"retry_count": _as_int(payload.get("retry_count"), default=0),
		},
		"source_payload": payload,
	}
