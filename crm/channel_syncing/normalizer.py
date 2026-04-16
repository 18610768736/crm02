from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list[str]:
	if value is None:
		return []
	if isinstance(value, (list, tuple, set)):
		return [str(item) for item in value if item]
	return [str(value)]


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
		"source_payload": payload,
	}
