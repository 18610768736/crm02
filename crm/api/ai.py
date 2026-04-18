import json

import frappe

from crm.ai.governance_repository import (
	list_audit_logs as list_stored_audit_logs,
	list_evidence_links as list_stored_evidence_links,
	persist_audit_log,
)
from crm.ai.memory_repository import (
	compile_customer_memory as compile_stored_customer_memory,
	get_customer_memory as get_stored_customer_memory,
	list_customer_memories as list_stored_customer_memories,
)
from crm.ai.repository import (
	get_suggestion,
	list_suggestions as list_stored_suggestions,
	update_suggestion_status,
)
from crm.ai.service import (
	build_panel_context as build_ai_panel_context,
	generate_suggestions as generate_ai_suggestions,
)


def _coerce_prompt(prompt: str | None) -> str | None:
	if prompt is None:
		return None
	return str(prompt).strip() or None


def _coerce_payload(value: dict | str | None) -> dict:
	if isinstance(value, dict):
		return value
	if isinstance(value, str) and value.strip():
		return json.loads(value)
	return {}


def _coerce_limit(value: int | str | None, default: int = 20) -> int:
	if value is None:
		return default
	return max(1, int(value))


def _validate_approval_decision(decision: str | None) -> str:
	allowed = {
		"accepted": "Accepted",
		"rejected": "Rejected",
		"applied": "Applied",
	}
	decision_key = str(decision or "Accepted").strip().lower()
	if decision_key in allowed:
		return allowed[decision_key]
	message = f"Unsupported decision: {decision}"
	if frappe:
		frappe.throw(message, frappe.ValidationError)
	raise ValueError(message)


@frappe.whitelist()
def get_panel_context(
	reference_doctype: str,
	reference_name: str,
	context_type: str = "deal_panel",
) -> dict:
	return build_ai_panel_context(reference_doctype, reference_name, context_type=context_type)


@frappe.whitelist()
def generate_suggestions(
	reference_doctype: str,
	reference_name: str,
	channel: str | None = None,
	prompt: str | None = None,
	context_type: str = "deal_panel",
	metadata: dict | str | None = None,
) -> dict:
	_coerce_payload(metadata)
	return generate_ai_suggestions(
		reference_doctype,
		reference_name,
		channel=channel,
		prompt=_coerce_prompt(prompt),
		context_type=context_type,
	)


@frappe.whitelist()
def list_suggestions(
	reference_doctype: str,
	reference_name: str,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_suggestions(reference_doctype, reference_name, limit=_coerce_limit(limit))
	return {
		"reference": {"doctype": reference_doctype, "name": reference_name},
		"items": items,
		"total_count": len(items),
	}


@frappe.whitelist()
def get_suggestion_detail(suggestion_id: str) -> dict:
	return get_suggestion(suggestion_id)


@frappe.whitelist()
def approve_suggestion(
	suggestion_id: str,
	decision: str = "Accepted",
	note: str | None = None,
) -> dict:
	approval_decision = _validate_approval_decision(decision)
	review_note = _coerce_prompt(note)
	try:
		updated_suggestion = update_suggestion_status(
			suggestion_id,
			approval_decision,
			review_note=review_note,
		)
	except KeyError as error:
		message = f"Suggestion not found: {suggestion_id}"
		if frappe:
			frappe.throw(message, frappe.DoesNotExistError)
		raise KeyError(message) from error

	reference = updated_suggestion.get("reference") or {}
	audit = persist_audit_log(
		{
			"action": "approve_suggestion",
			"status": approval_decision,
			"risk_level": "Medium" if approval_decision == "Rejected" else "Low",
			"source_type": "approval_ui",
			"source_ref": suggestion_id,
			"provider": "crm_frontend",
			"job_id": f"approval::{suggestion_id}",
			"message": f"Suggestion {approval_decision.lower()} via AI panel.",
			"payload": {
				"suggestion_id": suggestion_id,
				"decision": approval_decision,
				"note": review_note,
			},
			"reference": {
				"doctype": reference.get("doctype"),
				"name": reference.get("name"),
			},
		}
	)
	return {
		"status": "ok",
		"decision": approval_decision,
		"suggestion": updated_suggestion,
		"audit_id": audit["name"],
		"audit": audit,
	}


@frappe.whitelist()
def list_audit_logs(
	reference_doctype: str,
	reference_name: str,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_audit_logs(reference_doctype, reference_name, limit=_coerce_limit(limit))
	return {
		"reference": {"doctype": reference_doctype, "name": reference_name},
		"items": items,
		"total_count": len(items),
	}


@frappe.whitelist()
def list_evidence_links(
	reference_doctype: str,
	reference_name: str,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_evidence_links(reference_doctype, reference_name, limit=_coerce_limit(limit))
	return {
		"reference": {"doctype": reference_doctype, "name": reference_name},
		"items": items,
		"total_count": len(items),
	}


@frappe.whitelist()
def compile_customer_memory(reference_doctype: str, reference_name: str) -> dict:
	return compile_stored_customer_memory(reference_doctype, reference_name)


@frappe.whitelist()
def get_customer_memory(reference_doctype: str, reference_name: str) -> dict:
	return get_stored_customer_memory(reference_doctype, reference_name)


@frappe.whitelist()
def list_customer_memories(
	reference_doctype: str | None = None,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_customer_memories(reference_doctype=reference_doctype, limit=_coerce_limit(limit))
	return {
		"filters": {"reference_doctype": reference_doctype},
		"items": items,
		"total_count": len(items),
	}
