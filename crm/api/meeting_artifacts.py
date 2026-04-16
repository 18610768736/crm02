from __future__ import annotations

import json
import uuid
from copy import deepcopy

import frappe

from crm.api.channel_sync import ingest_event
from crm.channel_syncing.repository import (
	get_meeting_artifact,
	list_meeting_artifacts as list_stored_meeting_artifacts,
)

CRM_TASK_DOCTYPE = "CRM Task"
_VOLATILE_MEETING_TASKS: dict[str, dict] = {}


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


def _coerce_bool(value: bool | int | str | None) -> bool:
	if isinstance(value, bool):
		return value
	if value is None:
		return False
	return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _task_doctype_available() -> bool:
	return bool(frappe and frappe.db.exists("DocType", CRM_TASK_DOCTYPE))


def _reference_available(reference_doctype: str | None, reference_name: str | None) -> bool:
	if not reference_doctype or not reference_name:
		return False
	if not frappe:
		return False
	if not frappe.db.exists("DocType", reference_doctype):
		return False
	return bool(frappe.db.exists(reference_doctype, reference_name))


def _resolve_assignee(item: dict, fallback: str | None = None) -> str | None:
	candidate = item.get("assigned_to") or item.get("owner") or fallback
	if not candidate:
		return None
	candidate_text = str(candidate).strip()
	if "@" not in candidate_text:
		return fallback
	if frappe and frappe.db.exists("User", candidate_text):
		return candidate_text
	if not frappe:
		return candidate_text
	return fallback


def _task_payload_from_action(
	artifact: dict,
	action_item: dict,
	index: int,
	assigned_to: str | None = None,
	default_due_date: str | None = None,
) -> dict:
	title = (
		action_item.get("title")
		or action_item.get("task")
		or action_item.get("name")
		or f"Follow-up from meeting artifact #{index + 1}"
	)
	summary = artifact.get("summary") or ""
	description = action_item.get("description") or f"{summary}\n\nSource: {artifact.get('source_ref')}"
	reference = artifact.get("reference") or {}
	return {
		"title": title,
		"description": description,
		"priority": action_item.get("priority") or "Medium",
		"status": action_item.get("status") or "Todo",
		"assigned_to": _resolve_assignee(action_item, fallback=assigned_to),
		"due_date": action_item.get("due_date") or default_due_date,
		"reference_doctype": reference.get("doctype"),
		"reference_docname": reference.get("name"),
	}


def _to_task_detail(record: dict) -> dict:
	return {
		"name": record.get("name"),
		"title": record.get("title"),
		"description": record.get("description"),
		"priority": record.get("priority"),
		"status": record.get("status"),
		"assigned_to": record.get("assigned_to"),
		"due_date": record.get("due_date"),
		"reference": {
			"doctype": record.get("reference_doctype"),
			"name": record.get("reference_docname"),
		},
	}


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


@frappe.whitelist()
def convert_meeting_artifact_to_tasks(
	artifact_id: str,
	assigned_to: str | None = None,
	default_due_date: str | None = None,
	dry_run: bool | int | str | None = None,
) -> dict:
	artifact = get_meeting_artifact(artifact_id)
	action_items = artifact.get("action_items") or []
	if not action_items:
		action_items = [
			{
				"title": artifact.get("summary") or f"Follow up on meeting artifact {artifact_id}",
				"description": "Generated from meeting summary.",
			}
		]

	should_dry_run = _coerce_bool(dry_run)
	created_tasks: list[dict] = []

	for idx, action_item in enumerate(action_items):
		payload = _task_payload_from_action(
			artifact,
			action_item if isinstance(action_item, dict) else {"title": str(action_item)},
			idx,
			assigned_to=assigned_to,
			default_due_date=default_due_date,
		)
		if should_dry_run:
			created_tasks.append(_to_task_detail({"name": f"DRY-RUN-{idx + 1}", **payload}))
			continue

		reference_doctype = payload.get("reference_doctype")
		reference_docname = payload.get("reference_docname")
		if (
			_task_doctype_available()
			and (
				not reference_doctype
				or not reference_docname
				or _reference_available(reference_doctype, reference_docname)
			)
		):
			doc = frappe.get_doc({"doctype": CRM_TASK_DOCTYPE, **payload})
			doc.insert(ignore_permissions=True)
			created_tasks.append(_to_task_detail(doc.as_dict()))
			continue

		name = f"CRM-TASK-STUB-{uuid.uuid4().hex[:10]}"
		_VOLATILE_MEETING_TASKS[name] = {"name": name, **payload}
		created_tasks.append(_to_task_detail(deepcopy(_VOLATILE_MEETING_TASKS[name])))

	return {
		"artifact_id": artifact_id,
		"reference": artifact.get("reference"),
		"task_count": len(created_tasks),
		"dry_run": should_dry_run,
		"tasks": created_tasks,
	}
