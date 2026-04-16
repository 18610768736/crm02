from __future__ import annotations


def build_audit_record(
	reference_doctype: str,
	reference_name: str,
	action: str,
	status: str,
	source_type: str = "ai_service",
	source_ref: str | None = None,
	provider: str | None = None,
	job_id: str | None = None,
	risk_level: str = "Medium",
	message: str | None = None,
	payload: dict[str, object] | None = None,
) -> dict[str, object]:
	audit_key = f"{action}::{reference_doctype}::{reference_name}"
	return {
		"audit_key": audit_key,
		"action": action,
		"status": status,
		"risk_level": risk_level,
		"reference": {"doctype": reference_doctype, "name": reference_name},
		"source_type": source_type,
		"source_ref": source_ref or audit_key,
		"provider": provider,
		"job_id": job_id,
		"message": message,
		"payload": payload or {},
		"source": "crm.ai.audit",
	}
