from __future__ import annotations


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
