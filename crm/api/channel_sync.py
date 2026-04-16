import json

import frappe

from crm.ai.governance_repository import persist_audit_log, persist_evidence_links
from crm.ai.audit import build_audit_record
from crm.channel_syncing.connectors import normalize_connector_payload
from crm.channel_syncing.evidence import build_sync_evidence
from crm.channel_syncing.evidence import build_sync_evidence_links
from crm.channel_syncing.matcher import match_event_to_reference
from crm.channel_syncing.normalizer import normalize_event
from crm.channel_syncing.repository import (
	get_channel_workspace,
	get_conversation_thread,
	get_external_identity,
	get_meeting_artifact,
	get_sync_cursor,
	get_touchpoint,
	list_channel_workspaces as list_stored_channel_workspaces,
	list_conversation_threads as list_stored_conversation_threads,
	list_external_identities as list_stored_external_identities,
	list_meeting_artifacts as list_stored_meeting_artifacts,
	list_sync_cursors as list_stored_sync_cursors,
	list_touchpoints as list_stored_touchpoints,
	persist_channel_workspace,
	persist_conversation_thread,
	persist_external_identity,
	persist_meeting_artifact,
	persist_touchpoint,
	upsert_sync_cursor,
)


def _coerce_payload(payload: dict | str | None) -> dict:
	if isinstance(payload, dict):
		return payload
	if isinstance(payload, str) and payload.strip():
		return json.loads(payload)
	return {}


def _coerce_limit(value: int | str | None, default: int = 20) -> int:
	if value is None:
		return default
	return max(1, int(value))


@frappe.whitelist()
def ingest_event(channel: str, payload: dict | str | None = None) -> dict:
	source_payload = _coerce_payload(payload)
	connector_payload = normalize_connector_payload(channel, source_payload)
	normalized_event = normalize_event(channel, connector_payload)
	workspace = persist_channel_workspace(normalized_event)
	cursor = normalized_event.get("cursor") or {}
	cursor_key = cursor.get("key") or f"{channel}::{workspace['workspace_key']}"
	cursor_value = cursor.get("value") or normalized_event["external_id"]
	retry_count = int(cursor.get("retry_count") or 0)

	match_result = match_event_to_reference(normalized_event)
	evidence = build_sync_evidence(normalized_event)
	conversation_thread = persist_conversation_thread(normalized_event, match_result)
	touchpoint = persist_touchpoint(normalized_event, match_result, conversation_thread)
	external_identity = persist_external_identity(normalized_event, match_result)
	meeting_artifact = persist_meeting_artifact(
		normalized_event, match_result, conversation_thread
	)
	reference = match_result.get("reference") or {}
	evidence_links = build_sync_evidence_links(normalized_event)
	stored_evidence_links = persist_evidence_links(
		reference.get("doctype"),
		reference.get("name"),
		evidence_links,
		channel=channel,
	)
	external_id = normalized_event["external_id"]
	job_id = f"channel_sync_ingest::{channel}::{external_id}"
	audit = build_audit_record(
		reference.get("doctype") or "Channel Event",
		reference.get("name") or external_id,
		action="ingest_channel_event",
		status="Accepted",
		source_type="channel_sync",
		source_ref=f"{channel}::{external_id}",
		provider=channel,
		job_id=job_id,
		risk_level="Low",
		message="Ingested channel event and normalized payload.",
		payload={
			"match_strategy": match_result.get("strategy"),
			"thread_id": conversation_thread["name"],
		},
	)
	stored_audit = persist_audit_log(audit)
	stored_cursor = upsert_sync_cursor(
		channel=channel,
		cursor_key=cursor_key,
		cursor_value=cursor_value,
		workspace_id=workspace["name"],
		status="Succeeded",
		retry_count=retry_count,
		last_synced_at=normalized_event.get("occurred_at"),
		metadata={
			"event_id": normalized_event["external_id"],
			"thread_id": conversation_thread["name"],
			"touchpoint_id": touchpoint["name"],
		},
	)

	return {
		"ok": True,
		"status": "accepted",
		"channel": channel,
		"workspace_id": workspace["name"],
		"cursor_id": stored_cursor["name"],
		"normalized_event": normalized_event,
		"match": match_result,
		"evidence": evidence,
		"thread_id": conversation_thread["name"],
		"touchpoint_id": touchpoint["name"],
		"identity_id": external_identity["name"] if external_identity else None,
		"meeting_artifact_id": meeting_artifact["name"] if meeting_artifact else None,
		"audit_id": stored_audit["name"],
		"evidence_ids": [item["name"] for item in stored_evidence_links],
		"job": {
			"job_id": job_id,
			"job_type": "channel_sync_ingest",
			"status": "queued",
		},
	}


@frappe.whitelist()
def list_channel_workspaces(
	channel: str | None = None,
	status: str | None = None,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_channel_workspaces(
		channel=channel,
		status=status,
		limit=_coerce_limit(limit),
	)
	return {
		"filters": {"channel": channel, "status": status},
		"items": items,
		"total_count": len(items),
	}


@frappe.whitelist()
def get_channel_workspace_detail(workspace_id: str) -> dict:
	return get_channel_workspace(workspace_id)


@frappe.whitelist()
def list_sync_cursors(
	channel: str | None = None,
	workspace_id: str | None = None,
	status: str | None = None,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_sync_cursors(
		channel=channel,
		workspace_id=workspace_id,
		status=status,
		limit=_coerce_limit(limit),
	)
	return {
		"filters": {
			"channel": channel,
			"workspace_id": workspace_id,
			"status": status,
		},
		"items": items,
		"total_count": len(items),
	}


@frappe.whitelist()
def get_sync_cursor_detail(cursor_id: str) -> dict:
	return get_sync_cursor(cursor_id)


@frappe.whitelist()
def list_touchpoints(
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	channel: str | None = None,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_touchpoints(
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
def get_touchpoint_detail(touchpoint_id: str) -> dict:
	return get_touchpoint(touchpoint_id)


@frappe.whitelist()
def list_external_identities(
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	channel: str | None = None,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_external_identities(
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
def get_external_identity_detail(identity_id: str) -> dict:
	return get_external_identity(identity_id)


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
def list_conversation_threads(
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	channel: str | None = None,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_conversation_threads(
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
def get_conversation_thread_detail(thread_id: str) -> dict:
	return get_conversation_thread(thread_id)
