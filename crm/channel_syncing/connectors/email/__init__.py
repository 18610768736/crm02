from __future__ import annotations


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
