from __future__ import annotations

from crm.ai.schemas import AIJob


def build_job_stub(
	reference_doctype: str,
	reference_name: str,
	job_type: str = "ai_suggestions",
) -> AIJob:
	return {
		"job_id": f"{job_type}::{reference_doctype}::{reference_name}",
		"job_type": job_type,
		"status": "queued",
	}


def queue_suggestion_generation(reference_doctype: str, reference_name: str) -> AIJob:
	return build_job_stub(reference_doctype, reference_name)
