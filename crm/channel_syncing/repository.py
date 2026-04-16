from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any

try:
	import frappe
except ModuleNotFoundError:  # pragma: no cover - local non-Frappe environments
	frappe = None

EXTERNAL_IDENTITY_DOCTYPE = "External Identity"
MEETING_ARTIFACT_DOCTYPE = "Meeting Artifact"
TOUCHPOINT_DOCTYPE = "Touchpoint"
CONVERSATION_THREAD_DOCTYPE = "Conversation Thread"
CHANNEL_WORKSPACE_DOCTYPE = "Channel Workspace"
CHANNEL_CREDENTIAL_DOCTYPE = "Channel Credential"
SYNC_CURSOR_DOCTYPE = "Sync Cursor"

_VOLATILE_EXTERNAL_IDENTITIES: dict[str, dict[str, Any]] = {}
_VOLATILE_MEETING_ARTIFACTS: dict[str, dict[str, Any]] = {}
_VOLATILE_TOUCHPOINTS: dict[str, dict[str, Any]] = {}
_VOLATILE_CONVERSATION_THREADS: dict[str, dict[str, Any]] = {}
_VOLATILE_CHANNEL_WORKSPACES: dict[str, dict[str, Any]] = {}
_VOLATILE_CHANNEL_CREDENTIALS: dict[str, dict[str, Any]] = {}
_VOLATILE_SYNC_CURSORS: dict[str, dict[str, Any]] = {}


def _doc_type_available(doctype: str) -> bool:
	return bool(frappe and frappe.db.exists("DocType", doctype))


def _reference_available(reference_doctype: str | None, reference_name: str | None) -> bool:
	if not frappe:
		return False
	if not reference_doctype or not reference_name:
		return True
	if not _doc_type_available(reference_doctype):
		return False
	return bool(frappe.db.exists(reference_doctype, reference_name))


def _generate_name(prefix: str) -> str:
	if frappe:
		return f"{prefix}-{frappe.generate_hash(length=10)}"
	return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _json_dumps(value: Any) -> str:
	if value is None:
		value = {}
	return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None) -> Any:
	if not value:
		return {}
	return json.loads(value)


def _coerce_datetime(value: str | None) -> str | None:
	if not value:
		return None
	if frappe:
		try:
			return frappe.utils.get_datetime_str(frappe.utils.get_datetime(value))
		except Exception:
			pass
	try:
		return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
	except ValueError:
		return value


def _reference(match_result: dict[str, Any]) -> dict[str, Any]:
	return match_result.get("reference") or {}


def _reference_payload(record: dict[str, Any]) -> dict[str, str | None]:
	return {
		"doctype": record.get("reference_doctype"),
		"name": record.get("reference_name"),
	}


def _upsert_volatile(
	store: dict[str, dict[str, Any]],
	filters: dict[str, Any],
	payload: dict[str, Any],
) -> dict[str, Any]:
	for existing in store.values():
		if all(existing.get(key) == value for key, value in filters.items()):
			existing.update(payload)
			return deepcopy(existing)

	name = payload["name"]
	store[name] = deepcopy(payload)
	return deepcopy(store[name])


def _touchpoint_fields() -> list[str]:
	return [
		"name",
		"channel",
		"external_event_id",
		"thread_key",
		"touchpoint_type",
		"direction",
		"reference_doctype",
		"reference_name",
		"conversation_thread",
		"summary",
		"content_text",
		"counterparty_name",
		"occurred_at",
		"signal_json",
		"source_payload_json",
		"match_confidence",
		"match_strategy",
	]


def _external_identity_fields() -> list[str]:
	return [
		"name",
		"channel",
		"identity_key",
		"identity_type",
		"external_id",
		"external_name",
		"reference_doctype",
		"reference_name",
		"mapping_status",
		"confidence",
		"hints_json",
		"last_seen_at",
	]


def _meeting_artifact_fields() -> list[str]:
	return [
		"name",
		"channel",
		"artifact_key",
		"reference_doctype",
		"reference_name",
		"conversation_thread",
		"thread_key",
		"artifact_type",
		"source_type",
		"source_ref",
		"raw_content_ref",
		"summary",
		"action_items_json",
		"risk_signals_json",
		"processed_at",
	]


def _conversation_thread_fields() -> list[str]:
	return [
		"name",
		"channel",
		"thread_key",
		"status",
		"last_touchpoint_at",
		"touchpoint_count",
		"reference_doctype",
		"reference_name",
		"summary",
		"metadata_json",
	]


def _channel_workspace_fields() -> list[str]:
	return [
		"name",
		"channel",
		"workspace_key",
		"workspace_name",
		"tenant_id",
		"account_id",
		"status",
		"last_synced_at",
		"cursor_key",
		"cursor_value",
		"metadata_json",
	]


def _channel_credential_fields() -> list[str]:
	return [
		"name",
		"channel",
		"workspace",
		"credential_key",
		"auth_type",
		"base_url",
		"status",
		"expires_at",
		"last_validated_at",
		"failure_count",
		"metadata_json",
	]


def _sync_cursor_fields() -> list[str]:
	return [
		"name",
		"channel",
		"workspace",
		"cursor_key",
		"cursor_value",
		"status",
		"retry_count",
		"last_synced_at",
		"last_error",
		"metadata_json",
	]


def _to_touchpoint_detail(record: dict[str, Any]) -> dict[str, Any]:
	return {
		"name": record["name"],
		"channel": record.get("channel"),
		"external_event_id": record.get("external_event_id"),
		"thread_key": record.get("thread_key"),
		"touchpoint_type": record.get("touchpoint_type"),
		"direction": record.get("direction"),
		"summary": record.get("summary"),
		"content_text": record.get("content_text"),
		"counterparty_name": record.get("counterparty_name"),
		"conversation_thread": record.get("conversation_thread"),
		"occurred_at": record.get("occurred_at"),
		"match_confidence": float(record.get("match_confidence") or 0),
		"match_strategy": record.get("match_strategy"),
		"signal": _json_loads(record.get("signal_json")),
		"source_payload": _json_loads(record.get("source_payload_json")),
		"reference": _reference_payload(record),
	}


def _to_external_identity_detail(record: dict[str, Any]) -> dict[str, Any]:
	return {
		"name": record["name"],
		"channel": record.get("channel"),
		"identity_key": record.get("identity_key"),
		"identity_type": record.get("identity_type"),
		"external_id": record.get("external_id"),
		"external_name": record.get("external_name"),
		"mapping_status": record.get("mapping_status"),
		"confidence": float(record.get("confidence") or 0),
		"last_seen_at": record.get("last_seen_at"),
		"hints": _json_loads(record.get("hints_json")),
		"reference": _reference_payload(record),
	}


def _to_meeting_artifact_detail(record: dict[str, Any]) -> dict[str, Any]:
	return {
		"name": record["name"],
		"channel": record.get("channel"),
		"artifact_key": record.get("artifact_key"),
		"thread_key": record.get("thread_key"),
		"artifact_type": record.get("artifact_type"),
		"source_type": record.get("source_type"),
		"source_ref": record.get("source_ref"),
		"raw_content_ref": record.get("raw_content_ref"),
		"summary": record.get("summary"),
		"conversation_thread": record.get("conversation_thread"),
		"action_items": _json_loads(record.get("action_items_json")) or [],
		"risk_signals": _json_loads(record.get("risk_signals_json")) or [],
		"processed_at": record.get("processed_at"),
		"reference": _reference_payload(record),
	}


def _to_conversation_thread_detail(record: dict[str, Any]) -> dict[str, Any]:
	return {
		"name": record["name"],
		"channel": record.get("channel"),
		"thread_key": record.get("thread_key"),
		"status": record.get("status"),
		"last_touchpoint_at": record.get("last_touchpoint_at"),
		"touchpoint_count": int(record.get("touchpoint_count") or 0),
		"summary": record.get("summary"),
		"metadata": _json_loads(record.get("metadata_json")),
		"reference": _reference_payload(record),
	}


def _to_channel_workspace_detail(record: dict[str, Any]) -> dict[str, Any]:
	return {
		"name": record["name"],
		"channel": record.get("channel"),
		"workspace_key": record.get("workspace_key"),
		"workspace_name": record.get("workspace_name"),
		"tenant_id": record.get("tenant_id"),
		"account_id": record.get("account_id"),
		"status": record.get("status"),
		"last_synced_at": record.get("last_synced_at"),
		"cursor_key": record.get("cursor_key"),
		"cursor_value": record.get("cursor_value"),
		"metadata": _json_loads(record.get("metadata_json")),
	}


def _mask_secret(value: str | None) -> str | None:
	if not value:
		return None
	length = len(value)
	if length <= 4:
		return "*" * length
	return f"{value[:2]}{'*' * max(length - 4, 4)}{value[-2:]}"


def _to_channel_credential_detail(
	record: dict[str, Any],
	include_secrets: bool = False,
) -> dict[str, Any]:
	access_token = record.get("access_token")
	refresh_token = record.get("refresh_token")
	return {
		"name": record["name"],
		"channel": record.get("channel"),
		"workspace": record.get("workspace"),
		"credential_key": record.get("credential_key"),
		"auth_type": record.get("auth_type"),
		"base_url": record.get("base_url"),
		"status": record.get("status"),
		"expires_at": record.get("expires_at"),
		"last_validated_at": record.get("last_validated_at"),
		"failure_count": int(record.get("failure_count") or 0),
		"has_access_token": bool(access_token),
		"has_refresh_token": bool(refresh_token),
		"access_token": access_token if include_secrets else _mask_secret(access_token),
		"refresh_token": refresh_token if include_secrets else _mask_secret(refresh_token),
		"metadata": _json_loads(record.get("metadata_json")),
	}


def _to_sync_cursor_detail(record: dict[str, Any]) -> dict[str, Any]:
	return {
		"name": record["name"],
		"channel": record.get("channel"),
		"workspace": record.get("workspace"),
		"cursor_key": record.get("cursor_key"),
		"cursor_value": record.get("cursor_value"),
		"status": record.get("status"),
		"retry_count": int(record.get("retry_count") or 0),
		"last_synced_at": record.get("last_synced_at"),
		"last_error": record.get("last_error"),
		"metadata": _json_loads(record.get("metadata_json")),
	}


def persist_channel_workspace(normalized_event: dict[str, Any]) -> dict[str, Any]:
	workspace = normalized_event.get("workspace") or {}
	workspace_key = workspace.get("key") or f"{normalized_event.get('channel')}::default"
	filters = {"workspace_key": workspace_key}
	cursor = normalized_event.get("cursor") or {}
	payload = {
		"channel": normalized_event.get("channel"),
		"workspace_key": workspace_key,
		"workspace_name": workspace.get("name") or workspace_key,
		"tenant_id": workspace.get("tenant_id"),
		"account_id": workspace.get("account_id"),
		"status": "Active",
		"last_synced_at": _coerce_datetime(normalized_event.get("occurred_at")),
		"cursor_key": cursor.get("key"),
		"cursor_value": cursor.get("value"),
		"metadata_json": _json_dumps(
			{
				"event_type": normalized_event.get("event_type"),
				"last_external_id": normalized_event.get("external_id"),
			}
		),
	}

	if _doc_type_available(CHANNEL_WORKSPACE_DOCTYPE):
		name = frappe.db.exists(CHANNEL_WORKSPACE_DOCTYPE, filters)
		if name:
			frappe.db.set_value(CHANNEL_WORKSPACE_DOCTYPE, name, payload, update_modified=True)
			record = frappe.db.get_value(
				CHANNEL_WORKSPACE_DOCTYPE,
				name,
				_channel_workspace_fields(),
				as_dict=True,
			)
		else:
			try:
				doc = frappe.get_doc({"doctype": CHANNEL_WORKSPACE_DOCTYPE, **payload})
				doc.insert(ignore_permissions=True)
				record = doc.as_dict()
			except Exception:
				existing_name = frappe.db.exists(CHANNEL_WORKSPACE_DOCTYPE, filters)
				if not existing_name:
					raise
				frappe.db.set_value(CHANNEL_WORKSPACE_DOCTYPE, existing_name, payload, update_modified=True)
				record = frappe.db.get_value(
					CHANNEL_WORKSPACE_DOCTYPE,
					existing_name,
					_channel_workspace_fields(),
					as_dict=True,
				)
		return _to_channel_workspace_detail(record)

	record = _upsert_volatile(
		_VOLATILE_CHANNEL_WORKSPACES,
		filters,
		{"name": _generate_name("WS"), **payload},
	)
	return _to_channel_workspace_detail(record)


def _read_doc_password(doc: Any, fieldname: str) -> str | None:
	if not doc:
		return None
	try:
		return doc.get_password(fieldname)
	except Exception:
		return None


def _credential_record_from_doc(name: str) -> dict[str, Any]:
	doc = frappe.get_doc(CHANNEL_CREDENTIAL_DOCTYPE, name)
	record = {field: doc.get(field) for field in _channel_credential_fields()}
	record["name"] = doc.name
	record["access_token"] = _read_doc_password(doc, "access_token")
	record["refresh_token"] = _read_doc_password(doc, "refresh_token")
	return record


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
	metadata: dict[str, Any] | None = None,
	last_validated_at: str | None = None,
	failure_count: int | None = 0,
) -> dict[str, Any]:
	filters = {"credential_key": credential_key}
	payload = {
		"channel": channel,
		"workspace": workspace_id,
		"credential_key": credential_key,
		"auth_type": auth_type or "Bearer Token",
		"base_url": base_url,
		"status": status or "Active",
		"expires_at": _coerce_datetime(expires_at),
		"last_validated_at": _coerce_datetime(last_validated_at),
		"failure_count": int(failure_count or 0),
		"metadata_json": _json_dumps(metadata or {}),
	}

	if _doc_type_available(CHANNEL_CREDENTIAL_DOCTYPE):
		name = frappe.db.exists(CHANNEL_CREDENTIAL_DOCTYPE, filters)
		if name:
			doc = frappe.get_doc(CHANNEL_CREDENTIAL_DOCTYPE, name)
			doc.update(payload)
			if access_token is not None:
				doc.access_token = access_token
			if refresh_token is not None:
				doc.refresh_token = refresh_token
			doc.save(ignore_permissions=True)
			record = _credential_record_from_doc(doc.name)
		else:
			doc = frappe.get_doc({"doctype": CHANNEL_CREDENTIAL_DOCTYPE, **payload})
			if access_token is not None:
				doc.access_token = access_token
			if refresh_token is not None:
				doc.refresh_token = refresh_token
			doc.insert(ignore_permissions=True)
			record = _credential_record_from_doc(doc.name)
		return _to_channel_credential_detail(record)

	volatile_payload = {
		"name": _generate_name("CRE"),
		**payload,
		"access_token": access_token,
		"refresh_token": refresh_token,
	}
	record = _upsert_volatile(_VOLATILE_CHANNEL_CREDENTIALS, filters, volatile_payload)
	return _to_channel_credential_detail(record)


def upsert_sync_cursor(
	channel: str,
	cursor_key: str,
	cursor_value: str,
	workspace_id: str | None = None,
	status: str = "Succeeded",
	retry_count: int = 0,
	last_synced_at: str | None = None,
	last_error: str | None = None,
	metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
	filters = {"cursor_key": cursor_key}
	payload = {
		"channel": channel,
		"workspace": workspace_id,
		"cursor_key": cursor_key,
		"cursor_value": cursor_value,
		"status": status,
		"retry_count": retry_count,
		"last_synced_at": _coerce_datetime(last_synced_at),
		"last_error": last_error,
		"metadata_json": _json_dumps(metadata or {}),
	}

	if _doc_type_available(SYNC_CURSOR_DOCTYPE):
		name = frappe.db.exists(SYNC_CURSOR_DOCTYPE, filters)
		if name:
			frappe.db.set_value(SYNC_CURSOR_DOCTYPE, name, payload, update_modified=True)
			record = frappe.db.get_value(
				SYNC_CURSOR_DOCTYPE,
				name,
				_sync_cursor_fields(),
				as_dict=True,
			)
		else:
			try:
				doc = frappe.get_doc({"doctype": SYNC_CURSOR_DOCTYPE, **payload})
				doc.insert(ignore_permissions=True)
				record = doc.as_dict()
			except Exception:
				existing_name = frappe.db.exists(SYNC_CURSOR_DOCTYPE, filters)
				if not existing_name:
					raise
				frappe.db.set_value(SYNC_CURSOR_DOCTYPE, existing_name, payload, update_modified=True)
				record = frappe.db.get_value(
					SYNC_CURSOR_DOCTYPE,
					existing_name,
					_sync_cursor_fields(),
					as_dict=True,
				)
		return _to_sync_cursor_detail(record)

	record = _upsert_volatile(
		_VOLATILE_SYNC_CURSORS,
		filters,
		{"name": _generate_name("CUR"), **payload},
	)
	return _to_sync_cursor_detail(record)


def persist_conversation_thread(
	normalized_event: dict[str, Any],
	match_result: dict[str, Any],
) -> dict[str, Any]:
	reference = _reference(match_result)
	thread_match = match_result.get("thread_match") or {}
	thread_key = thread_match.get("thread_key") or normalized_event["thread_key"]
	filters = {"thread_key": thread_key}
	payload = {
		"channel": normalized_event["channel"],
		"thread_key": thread_key,
		"status": _resolve_thread_status(normalized_event),
		"last_touchpoint_at": normalized_event.get("occurred_at"),
		"touchpoint_count": 1,
		"reference_doctype": reference.get("doctype"),
		"reference_name": reference.get("name"),
		"summary": normalized_event["content"]["summary"],
		"metadata_json": _json_dumps(
			{
				"thread_strategy": thread_match.get("thread_strategy"),
				"thread_confidence": thread_match.get("thread_confidence"),
				"match_strategy": match_result.get("strategy"),
				"match_confidence": match_result.get("confidence"),
			}
		),
	}

	if _doc_type_available(CONVERSATION_THREAD_DOCTYPE) and _reference_available(
		reference.get("doctype"), reference.get("name")
	):
		name = frappe.db.exists(CONVERSATION_THREAD_DOCTYPE, filters)
		if name:
			doc = frappe.get_doc(CONVERSATION_THREAD_DOCTYPE, name)
			current_count = int(doc.get("touchpoint_count") or 0)
			doc.update(
				{
					**payload,
					"status": _resolve_thread_status(normalized_event, current_status=doc.get("status")),
					"touchpoint_count": current_count + 1,
				}
			)
			if not payload["last_touchpoint_at"]:
				doc.last_touchpoint_at = doc.get("last_touchpoint_at")
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": CONVERSATION_THREAD_DOCTYPE, **payload})
			doc.insert(ignore_permissions=True)
		return _to_conversation_thread_detail(doc.as_dict())

	existing = next(
		(
			record
			for record in _VOLATILE_CONVERSATION_THREADS.values()
			if all(record.get(key) == value for key, value in filters.items())
		),
		None,
	)
	if existing:
		payload["touchpoint_count"] = int(existing.get("touchpoint_count") or 0) + 1
		payload["status"] = _resolve_thread_status(
			normalized_event,
			current_status=existing.get("status"),
		)
		if not payload["last_touchpoint_at"]:
			payload["last_touchpoint_at"] = existing.get("last_touchpoint_at")
		volatile_payload = {"name": existing["name"], **payload}
	else:
		volatile_payload = {"name": _generate_name("THR"), **payload}

	record = _upsert_volatile(_VOLATILE_CONVERSATION_THREADS, filters, volatile_payload)
	return _to_conversation_thread_detail(record)


def persist_touchpoint(
	normalized_event: dict[str, Any],
	match_result: dict[str, Any],
	conversation_thread: dict[str, Any] | None = None,
) -> dict[str, Any]:
	reference = _reference(match_result)
	payload = {
		"channel": normalized_event["channel"],
		"external_event_id": normalized_event["external_id"],
		"thread_key": normalized_event["thread_key"],
		"touchpoint_type": _infer_touchpoint_type(normalized_event),
		"direction": _normalize_direction(normalized_event.get("direction")),
		"reference_doctype": reference.get("doctype"),
		"reference_name": reference.get("name"),
		"conversation_thread": conversation_thread.get("name") if conversation_thread else None,
		"summary": normalized_event["content"]["summary"],
		"content_text": normalized_event["content"]["text"],
		"counterparty_name": _extract_customer_name(normalized_event),
		"occurred_at": normalized_event.get("occurred_at"),
		"signal_json": _json_dumps(
			{
				"contact_hints": normalized_event.get("contact_hints", {}),
				"participants": normalized_event.get("participants", []),
			}
		),
		"source_payload_json": _json_dumps(normalized_event.get("source_payload", {})),
		"match_confidence": match_result.get("confidence") or 0,
		"match_strategy": match_result.get("strategy"),
	}
	filters = {"external_event_id": normalized_event["external_id"]}

	if _doc_type_available(TOUCHPOINT_DOCTYPE) and _reference_available(
		reference.get("doctype"), reference.get("name")
	):
		name = frappe.db.exists(TOUCHPOINT_DOCTYPE, filters)
		if name:
			doc = frappe.get_doc(TOUCHPOINT_DOCTYPE, name)
			doc.update(payload)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": TOUCHPOINT_DOCTYPE, **payload})
			doc.insert(ignore_permissions=True)
		return _to_touchpoint_detail(doc.as_dict())

	record = _upsert_volatile(
		_VOLATILE_TOUCHPOINTS,
		filters,
		{"name": _generate_name("TP"), **payload},
	)
	return _to_touchpoint_detail(record)


def persist_external_identity(
	normalized_event: dict[str, Any],
	match_result: dict[str, Any],
) -> dict[str, Any] | None:
	identity_candidates = _extract_identity_candidates(normalized_event)
	external_id = identity_candidates[0] if identity_candidates else None
	if not external_id:
		return None

	reference = _reference(match_result)
	channel = normalized_event["channel"]
	payload = {
		"channel": channel,
		"identity_key": f"{channel}::{external_id}",
		"identity_type": "Customer",
		"external_id": external_id,
		"external_name": _extract_customer_name(normalized_event),
		"reference_doctype": reference.get("doctype"),
		"reference_name": reference.get("name"),
		"mapping_status": _mapping_status(match_result),
		"confidence": match_result.get("confidence") or 0,
		"hints_json": _json_dumps(normalized_event.get("contact_hints", {})),
		"last_seen_at": normalized_event.get("occurred_at"),
	}
	filters = {"identity_key": payload["identity_key"]}

	if _doc_type_available(EXTERNAL_IDENTITY_DOCTYPE) and _reference_available(
		reference.get("doctype"), reference.get("name")
	):
		name = frappe.db.exists(EXTERNAL_IDENTITY_DOCTYPE, filters)
		if name:
			doc = frappe.get_doc(EXTERNAL_IDENTITY_DOCTYPE, name)
			doc.update(payload)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": EXTERNAL_IDENTITY_DOCTYPE, **payload})
			doc.insert(ignore_permissions=True)
		return _to_external_identity_detail(doc.as_dict())

	record = _upsert_volatile(
		_VOLATILE_EXTERNAL_IDENTITIES,
		filters,
		{"name": _generate_name("EXT-ID"), **payload},
	)
	return _to_external_identity_detail(record)


def match_reference_from_external_identity(
	normalized_event: dict[str, Any],
) -> dict[str, Any] | None:
	channel = normalized_event.get("channel")
	if not channel:
		return None

	identity_candidates = _extract_identity_candidates(normalized_event)
	if not identity_candidates:
		return None
	identity_keys = [f"{channel}::{candidate}" for candidate in identity_candidates]

	volatile_match = _match_reference_in_volatile_identities(identity_keys)
	if volatile_match:
		return volatile_match

	if not _doc_type_available(EXTERNAL_IDENTITY_DOCTYPE):
		return None

	record = frappe.get_all(
		EXTERNAL_IDENTITY_DOCTYPE,
		filters={
			"identity_key": ["in", identity_keys],
			"reference_doctype": ["is", "set"],
			"reference_name": ["is", "set"],
		},
		fields=["identity_key", "reference_doctype", "reference_name", "confidence"],
		order_by="confidence desc, modified desc",
		limit=1,
	)
	if not record:
		return None

	item = record[0]
	return {
		"reference": {
			"doctype": item.get("reference_doctype"),
			"name": item.get("reference_name"),
		},
		"confidence": float(item.get("confidence") or 0.85),
		"strategy": "external_identity_lookup",
	}


def persist_meeting_artifact(
	normalized_event: dict[str, Any],
	match_result: dict[str, Any],
	conversation_thread: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
	if not should_persist_meeting_artifact(normalized_event):
		return None

	reference = _reference(match_result)
	source_payload = normalized_event.get("source_payload", {})
	source_ref = source_payload.get("source_ref") or normalized_event["external_id"]
	payload = {
		"channel": normalized_event["channel"],
		"artifact_key": f"{normalized_event['channel']}::{source_ref}",
		"reference_doctype": reference.get("doctype"),
		"reference_name": reference.get("name"),
		"conversation_thread": conversation_thread.get("name") if conversation_thread else None,
		"thread_key": normalized_event["thread_key"],
		"artifact_type": source_payload.get("artifact_type") or "Minutes",
		"source_type": source_payload.get("source_type") or normalized_event["channel"].title(),
		"source_ref": source_ref,
		"raw_content_ref": source_payload.get("raw_content_ref")
		or f"{normalized_event['channel']}::{normalized_event['external_id']}",
		"summary": source_payload.get("meeting_summary") or normalized_event["content"]["summary"],
		"action_items_json": _json_dumps(source_payload.get("action_items") or []),
		"risk_signals_json": _json_dumps(source_payload.get("risk_signals") or []),
		"processed_at": source_payload.get("processed_at") or normalized_event.get("occurred_at"),
	}
	filters = {"artifact_key": payload["artifact_key"]}

	if _doc_type_available(MEETING_ARTIFACT_DOCTYPE) and _reference_available(
		reference.get("doctype"), reference.get("name")
	):
		name = frappe.db.exists(MEETING_ARTIFACT_DOCTYPE, filters)
		if name:
			doc = frappe.get_doc(MEETING_ARTIFACT_DOCTYPE, name)
			doc.update(payload)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": MEETING_ARTIFACT_DOCTYPE, **payload})
			doc.insert(ignore_permissions=True)
		return _to_meeting_artifact_detail(doc.as_dict())

	record = _upsert_volatile(
		_VOLATILE_MEETING_ARTIFACTS,
		filters,
		{"name": _generate_name("MEET"), **payload},
	)
	return _to_meeting_artifact_detail(record)


def list_touchpoints(
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	channel: str | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	filters = _build_reference_filters(reference_doctype, reference_name, channel)
	return _list_records(
		TOUCHPOINT_DOCTYPE,
		_VOLATILE_TOUCHPOINTS,
		_touchpoint_fields(),
		_to_touchpoint_detail,
		filters,
		"occurred_at desc",
		limit,
	)


def get_touchpoint(touchpoint_id: str) -> dict[str, Any]:
	return _get_record(
		TOUCHPOINT_DOCTYPE,
		_VOLATILE_TOUCHPOINTS,
		touchpoint_id,
		_to_touchpoint_detail,
	)


def list_external_identities(
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	channel: str | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	filters = _build_reference_filters(reference_doctype, reference_name, channel)
	return _list_records(
		EXTERNAL_IDENTITY_DOCTYPE,
		_VOLATILE_EXTERNAL_IDENTITIES,
		_external_identity_fields(),
		_to_external_identity_detail,
		filters,
		"modified desc",
		limit,
	)


def get_external_identity(identity_id: str) -> dict[str, Any]:
	return _get_record(
		EXTERNAL_IDENTITY_DOCTYPE,
		_VOLATILE_EXTERNAL_IDENTITIES,
		identity_id,
		_to_external_identity_detail,
	)


def list_meeting_artifacts(
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	channel: str | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	filters = _build_reference_filters(reference_doctype, reference_name, channel)
	return _list_records(
		MEETING_ARTIFACT_DOCTYPE,
		_VOLATILE_MEETING_ARTIFACTS,
		_meeting_artifact_fields(),
		_to_meeting_artifact_detail,
		filters,
		"processed_at desc",
		limit,
	)


def get_meeting_artifact(artifact_id: str) -> dict[str, Any]:
	return _get_record(
		MEETING_ARTIFACT_DOCTYPE,
		_VOLATILE_MEETING_ARTIFACTS,
		artifact_id,
		_to_meeting_artifact_detail,
	)


def list_conversation_threads(
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	channel: str | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	filters = _build_reference_filters(reference_doctype, reference_name, channel)
	return _list_records(
		CONVERSATION_THREAD_DOCTYPE,
		_VOLATILE_CONVERSATION_THREADS,
		_conversation_thread_fields(),
		_to_conversation_thread_detail,
		filters,
		"last_touchpoint_at desc, modified desc",
		limit,
	)


def get_conversation_thread(thread_id: str) -> dict[str, Any]:
	return _get_record(
		CONVERSATION_THREAD_DOCTYPE,
		_VOLATILE_CONVERSATION_THREADS,
		thread_id,
		_to_conversation_thread_detail,
	)


def list_channel_workspaces(
	channel: str | None = None,
	status: str | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	filters: dict[str, Any] = {}
	if channel:
		filters["channel"] = channel
	if status:
		filters["status"] = status
	return _list_records(
		CHANNEL_WORKSPACE_DOCTYPE,
		_VOLATILE_CHANNEL_WORKSPACES,
		_channel_workspace_fields(),
		_to_channel_workspace_detail,
		filters,
		"last_synced_at desc, modified desc",
		limit,
	)


def get_channel_workspace(workspace_id: str) -> dict[str, Any]:
	return _get_record(
		CHANNEL_WORKSPACE_DOCTYPE,
		_VOLATILE_CHANNEL_WORKSPACES,
		workspace_id,
		_to_channel_workspace_detail,
	)


def list_channel_credentials(
	channel: str | None = None,
	workspace_id: str | None = None,
	status: str | None = None,
	limit: int = 20,
	include_secrets: bool = False,
) -> list[dict[str, Any]]:
	filters: dict[str, Any] = {}
	if channel:
		filters["channel"] = channel
	if workspace_id:
		filters["workspace"] = workspace_id
	if status:
		filters["status"] = status

	items = []
	for record in _VOLATILE_CHANNEL_CREDENTIALS.values():
		if all(record.get(key) == value for key, value in filters.items()):
			items.append(_to_channel_credential_detail(record, include_secrets=include_secrets))

	if _doc_type_available(CHANNEL_CREDENTIAL_DOCTYPE):
		records = frappe.get_all(
			CHANNEL_CREDENTIAL_DOCTYPE,
			filters=filters,
			fields=["name", "credential_key"],
			order_by="last_validated_at desc, modified desc",
			limit=limit,
		)
		for record in records:
			name = record.get("name")
			if not name or name in _VOLATILE_CHANNEL_CREDENTIALS:
				continue
			items.append(
				_to_channel_credential_detail(
					_credential_record_from_doc(name),
					include_secrets=include_secrets,
				)
			)

	items.sort(key=lambda item: _sort_key(item.get("last_validated_at")), reverse=True)
	return items[:limit]


def get_channel_credential(
	credential_id: str,
	include_secrets: bool = False,
) -> dict[str, Any]:
	if credential_id in _VOLATILE_CHANNEL_CREDENTIALS:
		return _to_channel_credential_detail(
			_VOLATILE_CHANNEL_CREDENTIALS[credential_id],
			include_secrets=include_secrets,
		)

	if _doc_type_available(CHANNEL_CREDENTIAL_DOCTYPE) and frappe.db.exists(
		CHANNEL_CREDENTIAL_DOCTYPE, credential_id
	):
		record = _credential_record_from_doc(credential_id)
		return _to_channel_credential_detail(record, include_secrets=include_secrets)

	return _to_channel_credential_detail(
		_VOLATILE_CHANNEL_CREDENTIALS[credential_id],
		include_secrets=include_secrets,
	)


def list_sync_cursors(
	channel: str | None = None,
	workspace_id: str | None = None,
	status: str | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	filters: dict[str, Any] = {}
	if channel:
		filters["channel"] = channel
	if workspace_id:
		filters["workspace"] = workspace_id
	if status:
		filters["status"] = status
	return _list_records(
		SYNC_CURSOR_DOCTYPE,
		_VOLATILE_SYNC_CURSORS,
		_sync_cursor_fields(),
		_to_sync_cursor_detail,
		filters,
		"last_synced_at desc, modified desc",
		limit,
	)


def get_sync_cursor(cursor_id: str) -> dict[str, Any]:
	return _get_record(
		SYNC_CURSOR_DOCTYPE,
		_VOLATILE_SYNC_CURSORS,
		cursor_id,
		_to_sync_cursor_detail,
	)


def should_persist_meeting_artifact(normalized_event: dict[str, Any]) -> bool:
	event_type = str(normalized_event.get("event_type") or "")
	source_payload = normalized_event.get("source_payload", {})
	return bool(
		event_type.startswith("meeting")
		or source_payload.get("artifact_type")
		or source_payload.get("action_items")
		or source_payload.get("risk_signals")
	)


def _resolve_thread_status(
	normalized_event: dict[str, Any],
	current_status: str | None = None,
) -> str:
	source_payload = normalized_event.get("source_payload", {})
	explicit_status = source_payload.get("thread_status") or source_payload.get("status")
	if explicit_status in {"Active", "Archived", "Closed"}:
		return explicit_status

	event_type = str(normalized_event.get("event_type") or "")
	if event_type.endswith(".closed"):
		return "Closed"
	if event_type.endswith(".archived"):
		return "Archived"
	if source_payload.get("archived") is True:
		return "Archived"
	return current_status or "Active"


def _list_records(
	doctype: str,
	volatile_store: dict[str, dict[str, Any]],
	fields: list[str],
	transform: Any,
	filters: dict[str, Any],
	order_by: str,
	limit: int,
) -> list[dict[str, Any]]:
	items = []
	for record in volatile_store.values():
		if all(record.get(key) == value for key, value in filters.items()):
			items.append(transform(record))

	if _doc_type_available(doctype):
		records = frappe.get_all(
			doctype,
			filters=filters,
			fields=fields,
			order_by=order_by,
			limit=limit,
		)
		items.extend(
			transform(record) for record in records if record.get("name") not in volatile_store
		)

	items.sort(
		key=lambda item: _sort_key(
			item.get("occurred_at")
			or item.get("processed_at")
			or item.get("last_seen_at")
			or item.get("last_synced_at")
		),
		reverse=True,
	)
	return items[:limit]


def _get_record(
	doctype: str,
	volatile_store: dict[str, dict[str, Any]],
	record_id: str,
	transform: Any,
) -> dict[str, Any]:
	if record_id in volatile_store:
		return transform(volatile_store[record_id])

	if _doc_type_available(doctype) and frappe.db.exists(doctype, record_id):
		doc = frappe.get_doc(doctype, record_id)
		return transform(doc.as_dict())

	return transform(volatile_store[record_id])


def _build_reference_filters(
	reference_doctype: str | None,
	reference_name: str | None,
	channel: str | None,
) -> dict[str, Any]:
	filters: dict[str, Any] = {}
	if reference_doctype:
		filters["reference_doctype"] = reference_doctype
	if reference_name:
		filters["reference_name"] = reference_name
	if channel:
		filters["channel"] = channel
	return filters


def _sort_key(value: Any) -> str:
	if value is None:
		return ""
	if hasattr(value, "isoformat"):
		return value.isoformat()
	return str(value)


def _extract_customer_name(normalized_event: dict[str, Any]) -> str | None:
	for participant in normalized_event.get("participants", []):
		if participant.get("role") == "customer":
			return participant.get("label")
	return None


def _extract_external_identity(normalized_event: dict[str, Any]) -> str | None:
	candidates = _extract_identity_candidates(normalized_event)
	if not candidates:
		return None
	return candidates[0]


def _extract_identity_candidates(normalized_event: dict[str, Any]) -> list[str]:
	contact_hints = normalized_event.get("contact_hints", {})
	candidates: list[str] = []
	for key in ("external_user_ids", "emails", "phone_numbers", "display_names"):
		for value in contact_hints.get(key) or []:
			text = str(value).strip()
			if text and text not in candidates:
				candidates.append(text)
	return candidates


def _match_reference_in_volatile_identities(identity_keys: list[str]) -> dict[str, Any] | None:
	for record in _VOLATILE_EXTERNAL_IDENTITIES.values():
		if record.get("identity_key") not in identity_keys:
			continue
		reference_doctype = record.get("reference_doctype")
		reference_name = record.get("reference_name")
		if not reference_doctype or not reference_name:
			continue
		return {
			"reference": {"doctype": reference_doctype, "name": reference_name},
			"confidence": float(record.get("confidence") or 0.85),
			"strategy": "external_identity_lookup",
		}
	return None


def _mapping_status(match_result: dict[str, Any]) -> str:
	if match_result.get("reference"):
		return "Matched"
	if (match_result.get("confidence") or 0) > 0:
		return "Suggested"
	return "Unmatched"


def _normalize_direction(direction: str | None) -> str:
	if not direction:
		return "Inbound"
	return str(direction).capitalize()


def _infer_touchpoint_type(normalized_event: dict[str, Any]) -> str:
	event_type = str(normalized_event.get("event_type") or "")
	channel = normalized_event.get("channel")
	if event_type.startswith("meeting"):
		return "Meeting"
	if channel == "email":
		return "Email"
	return "Message"
