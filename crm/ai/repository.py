from __future__ import annotations

import json
import uuid
from copy import deepcopy
from typing import Any

try:
	import frappe
except ModuleNotFoundError:  # pragma: no cover - local non-Frappe environments
	frappe = None

AI_SUGGESTION_DOCTYPE = "AI Suggestion"

_VOLATILE_SUGGESTIONS: dict[str, dict[str, Any]] = {}


def _json_dumps(value: Any) -> str:
	if value is None:
		value = {}
	return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None) -> Any:
	if not value:
		return {}
	return json.loads(value)


def _generate_name(prefix: str) -> str:
	if frappe:
		return f"{prefix}-{frappe.generate_hash(length=10)}"
	return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _now() -> str | None:
	if frappe:
		return frappe.utils.now()
	return None


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


def _to_reference(record: dict[str, Any]) -> dict[str, str | None]:
	return {
		"doctype": record.get("reference_doctype"),
		"name": record.get("reference_name"),
	}


def _to_suggestion_detail(record: dict[str, Any]) -> dict[str, Any]:
	return {
		"name": record["name"],
		"key": record.get("suggestion_key"),
		"title": record.get("title"),
		"channel": record.get("channel"),
		"content": record.get("content"),
		"reason": record.get("reason"),
		"status": record.get("status") or "Open",
		"risk_level": record.get("risk_level") or "Medium",
		"evidence_count": int(record.get("evidence_count") or 0),
		"generated_by_agent": record.get("generated_by_agent"),
		"generated_at": record.get("generated_at"),
		"reference": _to_reference(record),
		"action_payload": _json_loads(record.get("action_payload_json")),
	}


def _upsert_volatile_suggestion(filters: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
	for existing in _VOLATILE_SUGGESTIONS.values():
		if all(existing.get(key) == value for key, value in filters.items()):
			existing.update(payload)
			return deepcopy(existing)

	name = payload["name"]
	_VOLATILE_SUGGESTIONS[name] = deepcopy(payload)
	return deepcopy(_VOLATILE_SUGGESTIONS[name])


def persist_suggestions(
	reference_doctype: str,
	reference_name: str,
	suggestions: list[dict[str, Any]],
	agent_request: dict[str, Any],
	evidence: dict[str, Any],
) -> list[dict[str, Any]]:
	stored_suggestions: list[dict[str, Any]] = []
	evidence_events = evidence.get("events", []) if isinstance(evidence, dict) else []

	for suggestion in suggestions:
		filters = {
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"suggestion_key": suggestion.get("key"),
			"channel": suggestion.get("channel"),
		}
		payload = {
			"suggestion_key": suggestion.get("key"),
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"suggestion_type": _infer_suggestion_type(suggestion),
			"title": suggestion.get("title"),
			"channel": suggestion.get("channel"),
			"content": suggestion.get("content"),
			"reason": suggestion.get("reason"),
			"status": "Open",
			"risk_level": _infer_risk_level(suggestion),
			"evidence_count": len(evidence_events),
			"generated_by_agent": agent_request.get("mode") or "crm_copilot",
			"generated_at": _now(),
			"action_payload_json": _json_dumps(
				{
					"reference": {"doctype": reference_doctype, "name": reference_name},
					"channel": suggestion.get("channel"),
					"prompt": agent_request.get("prompt"),
					"suggestion_key": suggestion.get("key"),
				}
			),
		}

		if _doc_type_available(AI_SUGGESTION_DOCTYPE) and _reference_available(
			reference_doctype, reference_name
		):
			name = frappe.db.exists(AI_SUGGESTION_DOCTYPE, filters)
			if name:
				doc = frappe.get_doc(AI_SUGGESTION_DOCTYPE, name)
				doc.update(payload)
				doc.save(ignore_permissions=True)
			else:
				doc = frappe.get_doc({"doctype": AI_SUGGESTION_DOCTYPE, **payload})
				doc.insert(ignore_permissions=True)
			stored_suggestions.append(_to_suggestion_detail(doc.as_dict()))
			continue

		volatile_payload = {"name": _generate_name("AI-SUG"), **payload}
		record = _upsert_volatile_suggestion(filters, volatile_payload)
		stored_suggestions.append(_to_suggestion_detail(record))

	return stored_suggestions


def list_suggestions(reference_doctype: str, reference_name: str, limit: int = 20) -> list[dict[str, Any]]:
	items = [
		_to_suggestion_detail(record)
		for record in _VOLATILE_SUGGESTIONS.values()
		if record.get("reference_doctype") == reference_doctype
		and record.get("reference_name") == reference_name
	]

	if _doc_type_available(AI_SUGGESTION_DOCTYPE):
		records = frappe.get_all(
			AI_SUGGESTION_DOCTYPE,
			filters={"reference_doctype": reference_doctype, "reference_name": reference_name},
			fields=[
				"name",
				"suggestion_key",
				"title",
				"channel",
				"content",
				"reason",
				"status",
				"risk_level",
				"evidence_count",
				"generated_by_agent",
				"generated_at",
				"reference_doctype",
				"reference_name",
				"action_payload_json",
			],
			order_by="modified desc",
			limit=limit,
		)
		items.extend(
			_to_suggestion_detail(record)
			for record in records
			if record.get("name") not in _VOLATILE_SUGGESTIONS
		)

	items.sort(key=lambda item: item.get("generated_at") or "", reverse=True)
	return items[:limit]


def get_suggestion(suggestion_id: str) -> dict[str, Any]:
	if suggestion_id in _VOLATILE_SUGGESTIONS:
		record = _VOLATILE_SUGGESTIONS[suggestion_id]
		return _to_suggestion_detail(record)

	if _doc_type_available(AI_SUGGESTION_DOCTYPE) and frappe.db.exists(
		AI_SUGGESTION_DOCTYPE, suggestion_id
	):
		doc = frappe.get_doc(AI_SUGGESTION_DOCTYPE, suggestion_id)
		return _to_suggestion_detail(doc.as_dict())

	record = _VOLATILE_SUGGESTIONS[suggestion_id]
	return _to_suggestion_detail(record)


def _infer_suggestion_type(suggestion: dict[str, Any]) -> str:
	key = str(suggestion.get("key") or "")
	if "draft" in key or suggestion.get("channel") in {"email", "qywx", "lark", "dingtalk"}:
		return "Draft"
	if "risk" in key:
		return "Risk"
	if "summary" in key:
		return "Summary"
	return "Next Step"


def _infer_risk_level(suggestion: dict[str, Any]) -> str:
	if suggestion.get("channel") == "crm_note":
		return "Low"
	return "Medium"
