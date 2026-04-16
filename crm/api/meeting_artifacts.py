from __future__ import annotations

import json
import uuid

import frappe

from crm.api.channel_sync import ingest_event
from crm.channel_syncing.repository import (
	get_meeting_artifact,
	list_meeting_artifacts as list_stored_meeting_artifacts,
)


def _coerce_limit(value: int | str | None, default: int = 20) -> int:
	if value is None:
		return default
	return max(1, int(value))


def _coerce_payload(value: dict | str | None) -> dict:
	if isinstance(value, dict):
		return value
	if isinstance(value, str) and value.strip():
		return json.loads(value)
	return {}


@frappe.whitelist()
def list_meeting_artifacts(
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	channel: str | None = None,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_meeting_artifacts(
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		channel=channel,
		limit=_coerce_limit(limit),
	)
	return {
		"filters": {
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"channel": channel,
		},
		"items": items,
		"total_count": len(items),
	}


@frappe.whitelist()
def get_meeting_artifact_detail(artifact_id: str) -> dict:
	return get_meeting_artifact(artifact_id)


@frappe.whitelist()
def import_meeting_artifact(
	channel: str = "lark",
	payload: dict | str | None = None,
) -> dict:
	source_payload = _coerce_payload(payload)
	event_id = source_payload.get("event_id") or f"import-meeting-{uuid.uuid4().hex[:10]}"
	conversation_id = source_payload.get("conversation_id") or source_payload.get("thread_key") or event_id
	import_payload = {
		"event_id": event_id,
		"event_type": source_payload.get("event_type") or "meeting.imported",
		"conversation_id": conversation_id,
		"occurred_at": source_payload.get("occurred_at"),
		"text": source_payload.get("text") or source_payload.get("content") or "Meeting content imported.",
		"summary": source_payload.get("summary") or "Meeting artifact imported.",
		"artifact_type": source_payload.get("artifact_type") or "Minutes",
		"source_type": source_payload.get("source_type") or channel.title(),
		"source_ref": source_payload.get("source_ref") or event_id,
		"raw_content_ref": source_payload.get("raw_content_ref"),
		"action_items": source_payload.get("action_items") or [],
		"risk_signals": source_payload.get("risk_signals") or [],
		"customer_name": source_payload.get("customer_name"),
		"owner_name": source_payload.get("owner_name"),
		"reference_doctype": source_payload.get("reference_doctype"),
		"reference_name": source_payload.get("reference_name"),
		"workspace_key": source_payload.get("workspace_key"),
		"workspace_name": source_payload.get("workspace_name"),
		"tenant_id": source_payload.get("tenant_id"),
		"account_id": source_payload.get("account_id"),
	}
	return ingest_event(channel, import_payload)
