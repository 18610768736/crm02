import frappe

from crm.ai.governance_repository import (
	list_audit_logs as list_stored_audit_logs,
	list_evidence_links as list_stored_evidence_links,
)


def _coerce_limit(value: int | str | None, default: int = 20) -> int:
	if value is None:
		return default
	return max(1, int(value))


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
