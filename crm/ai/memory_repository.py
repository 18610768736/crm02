from __future__ import annotations

import json
import uuid
from copy import deepcopy
from typing import Any

from crm.ai.governance_repository import list_evidence_links
from crm.ai.repository import list_suggestions
from crm.channel_syncing.repository import list_meeting_artifacts, list_touchpoints

try:
	import frappe
except ModuleNotFoundError:  # pragma: no cover - local non-Frappe environments
	frappe = None

CUSTOMER_MEMORY_DOCTYPE = "Customer Memory"
_VOLATILE_CUSTOMER_MEMORY: dict[str, dict[str, Any]] = {}


def _doc_type_available(doctype: str) -> bool:
	return bool(frappe and frappe.db.exists("DocType", doctype))


def _reference_available(reference_doctype: str | None, reference_name: str | None) -> bool:
	if not frappe:
		return False
	if not reference_doctype or not reference_name:
		return False
	if not _doc_type_available(reference_doctype):
		return False
	return bool(frappe.db.exists(reference_doctype, reference_name))


def _generate_name(prefix: str) -> str:
	if frappe:
		return f"{prefix}-{frappe.generate_hash(length=10)}"
	return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _json_dumps(value: Any) -> str:
	return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None) -> Any:
	if not value:
		return {}
	return json.loads(value)


def _to_detail(record: dict[str, Any]) -> dict[str, Any]:
	return {
		"name": record["name"],
		"memory_key": record.get("memory_key"),
		"summary": record.get("summary"),
		"source_count": int(record.get("source_count") or 0),
		"last_compiled_at": record.get("last_compiled_at"),
		"signals": _json_loads(record.get("signals_json")),
		"reference": {
			"doctype": record.get("reference_doctype"),
			"name": record.get("reference_name"),
		},
	}


def _memory_fields() -> list[str]:
	return [
		"name",
		"memory_key",
		"reference_doctype",
		"reference_name",
		"summary",
		"source_count",
		"last_compiled_at",
		"signals_json",
	]


def _upsert_volatile(filters: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
	for existing in _VOLATILE_CUSTOMER_MEMORY.values():
		if all(existing.get(key) == value for key, value in filters.items()):
			existing.update(payload)
			return deepcopy(existing)
	_VOLATILE_CUSTOMER_MEMORY[payload["name"]] = deepcopy(payload)
	return deepcopy(payload)


def _build_memory_summary(
	reference_doctype: str,
	reference_name: str,
	touchpoints: list[dict[str, Any]],
	meeting_artifacts: list[dict[str, Any]],
	suggestions: list[dict[str, Any]],
) -> str:
	if not touchpoints and not meeting_artifacts and not suggestions:
		return f"{reference_doctype} {reference_name} 暂无可汇总的客户记忆。"

	latest_touchpoint = touchpoints[0] if touchpoints else None
	latest_touchpoint_text = (
		f"最近触点：{latest_touchpoint.get('summary') or latest_touchpoint.get('content_text')}"
		if latest_touchpoint
		else "最近触点：暂无"
	)
	latest_suggestion = suggestions[0] if suggestions else None
	suggestion_text = (
		f"当前建议：{latest_suggestion.get('title')}"
		if latest_suggestion
		else "当前建议：暂无"
	)
	meeting_text = f"会议纪要数：{len(meeting_artifacts)}"
	return "；".join([latest_touchpoint_text, suggestion_text, meeting_text])


def _build_signals(
	touchpoints: list[dict[str, Any]],
	meeting_artifacts: list[dict[str, Any]],
	suggestions: list[dict[str, Any]],
	evidence_links: list[dict[str, Any]],
) -> dict[str, Any]:
	channel_counter: dict[str, int] = {}
	for item in touchpoints:
		channel = item.get("channel") or "unknown"
		channel_counter[channel] = channel_counter.get(channel, 0) + 1

	open_suggestions = [item for item in suggestions if item.get("status") in {None, "Open"}]
	total_action_items = sum(len(item.get("action_items") or []) for item in meeting_artifacts)

	return {
		"touchpoint_count": len(touchpoints),
		"channels": channel_counter,
		"latest_touchpoint_at": touchpoints[0].get("occurred_at") if touchpoints else None,
		"meeting_artifact_count": len(meeting_artifacts),
		"meeting_action_item_count": total_action_items,
		"suggestion_count": len(suggestions),
		"open_suggestion_count": len(open_suggestions),
		"evidence_count": len(evidence_links),
	}


def upsert_customer_memory(
	reference_doctype: str,
	reference_name: str,
	summary: str,
	signals: dict[str, Any],
	source_count: int,
) -> dict[str, Any]:
	memory_key = f"{reference_doctype}::{reference_name}"
	filters = {"memory_key": memory_key}
	payload = {
		"memory_key": memory_key,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"summary": summary,
		"signals_json": _json_dumps(signals),
		"source_count": int(source_count or 0),
		"last_compiled_at": frappe.utils.now() if frappe else None,
	}

	if _doc_type_available(CUSTOMER_MEMORY_DOCTYPE) and _reference_available(
		reference_doctype, reference_name
	):
		name = frappe.db.exists(CUSTOMER_MEMORY_DOCTYPE, filters)
		if name:
			doc = frappe.get_doc(CUSTOMER_MEMORY_DOCTYPE, name)
			doc.update(payload)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": CUSTOMER_MEMORY_DOCTYPE, **payload})
			doc.insert(ignore_permissions=True)
		return _to_detail(doc.as_dict())

	record = _upsert_volatile(filters, {"name": _generate_name("MEM"), **payload})
	return _to_detail(record)


def compile_customer_memory(reference_doctype: str, reference_name: str) -> dict[str, Any]:
	touchpoints = list_touchpoints(reference_doctype, reference_name, limit=20)
	meeting_artifacts = list_meeting_artifacts(reference_doctype, reference_name, limit=10)
	suggestions = list_suggestions(reference_doctype, reference_name, limit=10)
	evidence_links = list_evidence_links(reference_doctype, reference_name, limit=20)
	summary = _build_memory_summary(
		reference_doctype,
		reference_name,
		touchpoints,
		meeting_artifacts,
		suggestions,
	)
	signals = _build_signals(touchpoints, meeting_artifacts, suggestions, evidence_links)
	source_count = len(touchpoints) + len(meeting_artifacts) + len(suggestions) + len(evidence_links)
	return upsert_customer_memory(reference_doctype, reference_name, summary, signals, source_count)


def get_customer_memory(reference_doctype: str, reference_name: str) -> dict[str, Any]:
	memory_key = f"{reference_doctype}::{reference_name}"
	if _doc_type_available(CUSTOMER_MEMORY_DOCTYPE):
		name = frappe.db.exists(CUSTOMER_MEMORY_DOCTYPE, {"memory_key": memory_key})
		if name:
			doc = frappe.get_doc(CUSTOMER_MEMORY_DOCTYPE, name)
			return _to_detail(doc.as_dict())

	for record in _VOLATILE_CUSTOMER_MEMORY.values():
		if record.get("memory_key") == memory_key:
			return _to_detail(record)

	return {
		"name": None,
		"memory_key": memory_key,
		"summary": None,
		"source_count": 0,
		"last_compiled_at": None,
		"signals": {},
		"reference": {"doctype": reference_doctype, "name": reference_name},
	}


def list_customer_memories(
	reference_doctype: str | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	items = [
		_to_detail(record)
		for record in _VOLATILE_CUSTOMER_MEMORY.values()
		if not reference_doctype or record.get("reference_doctype") == reference_doctype
	]

	if _doc_type_available(CUSTOMER_MEMORY_DOCTYPE):
		filters = {}
		if reference_doctype:
			filters["reference_doctype"] = reference_doctype
		records = frappe.get_all(
			CUSTOMER_MEMORY_DOCTYPE,
			filters=filters,
			fields=_memory_fields(),
			order_by="last_compiled_at desc, modified desc",
			limit=limit,
		)
		items.extend(
			_to_detail(record)
			for record in records
			if record.get("name") not in _VOLATILE_CUSTOMER_MEMORY
		)

	items.sort(key=lambda item: str(item.get("last_compiled_at") or ""), reverse=True)
	return items[:limit]

