import json

import frappe

from crm.ai.governance_repository import persist_audit_log, persist_evidence_links
from crm.ai.audit import build_audit_record
from crm.ai.lead_agent import ensure_reference_for_event
from crm.channel_syncing.background_sync import sync_all_channels, sync_channel
from crm.channel_syncing.alerts import emit_sync_alert, list_sync_alerts as list_stored_sync_alerts
from crm.channel_syncing.connectors import normalize_connector_payload
from crm.channel_syncing.evidence import build_sync_evidence
from crm.channel_syncing.evidence import build_sync_evidence_links
from crm.channel_syncing.matcher import match_event_to_reference
from crm.channel_syncing.normalizer import normalize_event
from crm.channel_syncing.repository import (
	get_channel_workspace,
	get_channel_credential,
	get_conversation_thread,
	get_external_identity,
	get_meeting_artifact,
	get_sync_cursor,
	get_touchpoint,
	list_channel_workspaces as list_stored_channel_workspaces,
	list_channel_credentials as list_stored_channel_credentials,
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
	upsert_channel_credential as upsert_stored_channel_credential,
	upsert_sync_cursor,
)
from crm.channel_syncing.security import verify_webhook_request


def _coerce_payload(payload: dict | str | None) -> tuple[dict, str]:
	if isinstance(payload, dict):
		return payload, json.dumps(payload, ensure_ascii=False, sort_keys=True)
	if isinstance(payload, str) and payload.strip():
		return json.loads(payload), payload
	return {}, "{}"


def _coerce_dict(value: dict | str | None) -> dict:
	if isinstance(value, dict):
		return value
	if isinstance(value, str) and value.strip():
		return json.loads(value)
	return {}


def _coerce_limit(value: int | str | None, default: int = 20) -> int:
	if value is None:
		return default
	return max(1, int(value))


def _coerce_bool(value: bool | int | str | None) -> bool | None:
	if value is None:
		return None
	if isinstance(value, bool):
		return value
	text = str(value).strip().lower()
	return text in {"1", "true", "yes", "on"}


def _raw_event_id(payload: dict) -> str:
	return (
		payload.get("event_id")
		or payload.get("external_id")
		or payload.get("message_id")
		or payload.get("msgid")
		or "pending-external-id"
	)


def _require_sync_admin() -> None:
	frappe.only_for(["System Manager"], True)


@frappe.whitelist()
def ingest_event(
	channel: str,
	payload: dict | str | None = None,
	signature: str | None = None,
	timestamp: str | int | None = None,
	nonce: str | None = None,
	verify_signature: bool | int | str | None = None,
) -> dict:
	source_payload, raw_payload = _coerce_payload(payload)
	enforce_signature = _coerce_bool(verify_signature)
	verification = verify_webhook_request(
		channel=channel,
		raw_payload=raw_payload,
		payload=source_payload,
		signature=signature,
		timestamp=timestamp,
		nonce=nonce,
		verify_signature=enforce_signature,
	)
	if verification.get("required") and not verification.get("verified"):
		failure_external_id = _raw_event_id(source_payload)
		cursor_key = source_payload.get("cursor_key") or source_payload.get("workspace_key") or f"{channel}::default"
		cursor_value = source_payload.get("cursor_value") or source_payload.get("event_time") or failure_external_id
		retry_count = int(source_payload.get("retry_count") or 0) + 1
		stored_cursor = upsert_sync_cursor(
			channel=channel,
			cursor_key=cursor_key,
			cursor_value=cursor_value,
			status="Failed",
			retry_count=retry_count,
			last_error=verification.get("reason") or "signature_verification_failed",
			metadata={
				"mode": "webhook_guard",
				"event_id": failure_external_id,
				"verification": verification,
			},
		)
		alert = emit_sync_alert(
			channel=channel,
			code="webhook_signature_failed",
			severity="error",
			message=verification.get("error") or "Webhook signature verification failed.",
			context={
				"cursor_id": stored_cursor["name"],
				"reason": verification.get("reason"),
				"event_id": failure_external_id,
			},
		)
		frappe.throw(
			f"{verification.get('error') or 'Webhook signature verification failed.'} "
			f"(alert: {alert['name']})"
		)

	connector_payload = normalize_connector_payload(channel, source_payload)
	normalized_event = normalize_event(channel, connector_payload)
	workspace = persist_channel_workspace(normalized_event)
	cursor = normalized_event.get("cursor") or {}
	cursor_key = cursor.get("key") or f"{channel}::{workspace['workspace_key']}"
	cursor_value = cursor.get("value") or normalized_event["external_id"]
	retry_count = int(cursor.get("retry_count") or 0)

	match_result = match_event_to_reference(normalized_event)
	match_result, auto_profile = ensure_reference_for_event(normalized_event, match_result)
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
			"auto_profile_reference": (auto_profile or {}).get("reference"),
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
		"auto_profile": auto_profile,
		"evidence": evidence,
		"security": verification,
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
def upsert_channel_credential(
	channel: str,
	credential_key: str,
	workspace_id: str | None = None,
	auth_type: str | None = "Bearer Token",
	base_url: str | None = None,
	access_token: str | None = None,
	refresh_token: str | None = None,
	status: str | None = "Active",
	expires_at: str | None = None,
	metadata: dict | str | None = None,
) -> dict:
	_require_sync_admin()
	credential = upsert_stored_channel_credential(
		channel=channel,
		workspace_id=workspace_id,
		credential_key=credential_key,
		auth_type=auth_type,
		base_url=base_url,
		access_token=access_token,
		refresh_token=refresh_token,
		status=status,
		expires_at=expires_at,
		metadata=_coerce_dict(metadata),
	)
	return {"ok": True, "credential": credential}


@frappe.whitelist()
def list_channel_credentials(
	channel: str | None = None,
	workspace_id: str | None = None,
	status: str | None = None,
	limit: int | str | None = 20,
) -> dict:
	_require_sync_admin()
	items = list_stored_channel_credentials(
		channel=channel,
		workspace_id=workspace_id,
		status=status,
		limit=_coerce_limit(limit),
		include_secrets=False,
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
def get_channel_credential_detail(
	credential_id: str,
) -> dict:
	_require_sync_admin()
	return get_channel_credential(credential_id, include_secrets=False)


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
def run_pull_sync(
	channel: str,
	credential_id: str | None = None,
	cursor_key: str | None = None,
	cursor_value: str | None = None,
	limit: int | str | None = 20,
	max_retries: int | str | None = 1,
) -> dict:
	_require_sync_admin()
	return sync_channel(
		channel=channel,
		credential_id=credential_id,
		cursor_key=cursor_key,
		cursor_value=cursor_value,
		limit=_coerce_limit(limit),
		max_retries=max(0, int(max_retries or 0)),
	)


@frappe.whitelist()
def run_pull_sync_all(
	channels: list[str] | str | None = None,
	limit: int | str | None = 20,
	max_retries: int | str | None = 1,
) -> dict:
	_require_sync_admin()
	target_channels = channels
	if isinstance(channels, str):
		target_channels = [item.strip() for item in channels.split(",") if item.strip()]
	results = sync_all_channels(
		channels=target_channels if isinstance(target_channels, list) else None,
		limit=_coerce_limit(limit),
		max_retries=max(0, int(max_retries or 0)),
	)
	return {
		"items": results,
		"total_count": len(results),
		"succeeded_count": len([item for item in results if item.get("status") == "succeeded"]),
	}


@frappe.whitelist()
def list_sync_alerts(
	channel: str | None = None,
	severity: str | None = None,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_sync_alerts(
		channel=channel,
		severity=severity,
		limit=_coerce_limit(limit),
	)
	return {
		"filters": {"channel": channel, "severity": severity},
		"items": items,
		"total_count": len(items),
	}


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
