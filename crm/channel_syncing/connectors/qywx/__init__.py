from __future__ import annotations


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
