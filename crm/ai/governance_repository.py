from __future__ import annotations

import json
import uuid
from copy import deepcopy
from typing import Any

try:
	import frappe
except ModuleNotFoundError:  # pragma: no cover - local non-Frappe environments
	frappe = None

AUDIT_LOG_DOCTYPE = "Audit Log"
EVIDENCE_LINK_DOCTYPE = "Evidence Link"

_VOLATILE_AUDIT_LOGS: dict[str, dict[str, Any]] = {}
_VOLATILE_EVIDENCE_LINKS: dict[str, dict[str, Any]] = {}


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


def _json_dumps(value: Any) -> str:
	return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None) -> Any:
	if not value:
		return {}
	return json.loads(value)


def _now() -> str | None:
	if frappe:
		return frappe.utils.now()
	return None


def _generate_name(prefix: str) -> str:
	if frappe:
		return f"{prefix}-{frappe.generate_hash(length=10)}"
	return f"{prefix}-{uuid.uuid4().hex[:10]}"


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


def _audit_fields() -> list[str]:
	return [
		"name",
		"audit_key",
		"action",
		"status",
		"risk_level",
		"reference_doctype",
		"reference_name",
		"source_type",
		"source_ref",
		"provider",
		"job_id",
		"message",
		"payload_json",
		"logged_at",
	]


def _evidence_fields() -> list[str]:
	return [
		"name",
		"evidence_key",
		"title",
		"channel",
		"source_type",
		"source_ref",
		"reference_doctype",
		"reference_name",
		"summary",
		"evidence_url",
		"raw_payload_json",
		"captured_at",
	]


def _to_audit_detail(record: dict[str, Any]) -> dict[str, Any]:
	return {
		"name": record["name"],
		"audit_key": record.get("audit_key"),
		"action": record.get("action"),
		"status": record.get("status"),
		"risk_level": record.get("risk_level"),
		"source_type": record.get("source_type"),
		"source_ref": record.get("source_ref"),
		"provider": record.get("provider"),
		"job_id": record.get("job_id"),
		"message": record.get("message"),
		"payload": _json_loads(record.get("payload_json")),
		"logged_at": record.get("logged_at"),
		"reference": {
			"doctype": record.get("reference_doctype"),
			"name": record.get("reference_name"),
		},
	}


def _to_evidence_detail(record: dict[str, Any]) -> dict[str, Any]:
	return {
		"name": record["name"],
		"evidence_key": record.get("evidence_key"),
		"title": record.get("title"),
		"channel": record.get("channel"),
		"source_type": record.get("source_type"),
		"source_ref": record.get("source_ref"),
		"summary": record.get("summary"),
		"evidence_url": record.get("evidence_url"),
		"raw_payload": _json_loads(record.get("raw_payload_json")),
		"captured_at": record.get("captured_at"),
		"reference": {
			"doctype": record.get("reference_doctype"),
			"name": record.get("reference_name"),
		},
	}


def persist_audit_log(record: dict[str, Any]) -> dict[str, Any]:
	reference = record.get("reference") or {}
	reference_doctype = reference.get("doctype")
	reference_name = reference.get("name")
	action = str(record.get("action") or "unknown_action")
	source_ref = record.get("source_ref") or record.get("job_id") or "unknown-source"
	audit_key = record.get("audit_key") or f"{action}::{source_ref}"
	filters = {"audit_key": audit_key}
	payload = {
		"audit_key": audit_key,
		"action": action,
		"status": record.get("status") or "Queued",
		"risk_level": record.get("risk_level") or "Medium",
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"source_type": record.get("source_type") or "application",
		"source_ref": record.get("source_ref"),
		"provider": record.get("provider"),
		"job_id": record.get("job_id"),
		"message": record.get("message"),
		"payload_json": _json_dumps(record.get("payload")),
		"logged_at": record.get("logged_at") or _now(),
	}

	if _doc_type_available(AUDIT_LOG_DOCTYPE) and _reference_available(
		reference_doctype, reference_name
	):
		name = frappe.db.exists(AUDIT_LOG_DOCTYPE, filters)
		if name:
			doc = frappe.get_doc(AUDIT_LOG_DOCTYPE, name)
			doc.update(payload)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": AUDIT_LOG_DOCTYPE, **payload})
			doc.insert(ignore_permissions=True)
		return _to_audit_detail(doc.as_dict())

	volatile_payload = {"name": _generate_name("AUD"), **payload}
	stored = _upsert_volatile(_VOLATILE_AUDIT_LOGS, filters, volatile_payload)
	return _to_audit_detail(stored)


def persist_evidence_links(
	reference_doctype: str | None,
	reference_name: str | None,
	evidence_links: list[dict[str, Any]],
	channel: str | None = None,
) -> list[dict[str, Any]]:
	stored_links: list[dict[str, Any]] = []
	for evidence in evidence_links:
		evidence_key = evidence.get("evidence_key") or _generate_name("EVD")
		filters = {"evidence_key": evidence_key}
		payload = {
			"evidence_key": evidence_key,
			"title": evidence.get("title"),
			"channel": evidence.get("channel") or channel,
			"source_type": evidence.get("source_type"),
			"source_ref": evidence.get("source_ref"),
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"summary": evidence.get("summary"),
			"evidence_url": evidence.get("evidence_url"),
			"raw_payload_json": _json_dumps(evidence.get("raw_payload")),
			"captured_at": evidence.get("captured_at") or _now(),
		}

		if _doc_type_available(EVIDENCE_LINK_DOCTYPE) and _reference_available(
			reference_doctype, reference_name
		):
			name = frappe.db.exists(EVIDENCE_LINK_DOCTYPE, filters)
			if name:
				doc = frappe.get_doc(EVIDENCE_LINK_DOCTYPE, name)
				doc.update(payload)
				doc.save(ignore_permissions=True)
			else:
				doc = frappe.get_doc({"doctype": EVIDENCE_LINK_DOCTYPE, **payload})
				doc.insert(ignore_permissions=True)
			stored_links.append(_to_evidence_detail(doc.as_dict()))
			continue

		volatile_payload = {"name": _generate_name("EVD"), **payload}
		stored = _upsert_volatile(_VOLATILE_EVIDENCE_LINKS, filters, volatile_payload)
		stored_links.append(_to_evidence_detail(stored))

	return stored_links


def list_audit_logs(reference_doctype: str, reference_name: str, limit: int = 20) -> list[dict[str, Any]]:
	items = [
		_to_audit_detail(record)
		for record in _VOLATILE_AUDIT_LOGS.values()
		if record.get("reference_doctype") == reference_doctype
		and record.get("reference_name") == reference_name
	]

	if _doc_type_available(AUDIT_LOG_DOCTYPE):
		records = frappe.get_all(
			AUDIT_LOG_DOCTYPE,
			filters={"reference_doctype": reference_doctype, "reference_name": reference_name},
			fields=_audit_fields(),
			order_by="logged_at desc, modified desc",
			limit=limit,
		)
		items.extend(
			_to_audit_detail(record)
			for record in records
			if record.get("name") not in _VOLATILE_AUDIT_LOGS
		)

	items.sort(key=lambda item: item.get("logged_at") or "", reverse=True)
	return items[:limit]


def list_evidence_links(
	reference_doctype: str,
	reference_name: str,
	limit: int = 20,
) -> list[dict[str, Any]]:
	items = [
		_to_evidence_detail(record)
		for record in _VOLATILE_EVIDENCE_LINKS.values()
		if record.get("reference_doctype") == reference_doctype
		and record.get("reference_name") == reference_name
	]

	if _doc_type_available(EVIDENCE_LINK_DOCTYPE):
		records = frappe.get_all(
			EVIDENCE_LINK_DOCTYPE,
			filters={"reference_doctype": reference_doctype, "reference_name": reference_name},
			fields=_evidence_fields(),
			order_by="captured_at desc, modified desc",
			limit=limit,
		)
		items.extend(
			_to_evidence_detail(record)
			for record in records
			if record.get("name") not in _VOLATILE_EVIDENCE_LINKS
		)

	items.sort(key=lambda item: item.get("captured_at") or "", reverse=True)
	return items[:limit]
