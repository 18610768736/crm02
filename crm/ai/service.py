from __future__ import annotations

from crm.ai.agent_client import build_agent_request, execute_agent_request
from crm.ai.approvals import build_approval_request
from crm.ai.audit import build_audit_record
from crm.ai.background import build_job_stub
from crm.ai.context_builder import build_panel_context as build_base_panel_context
from crm.ai.evidence import build_evidence_links, build_evidence_packet
from crm.ai.governance_repository import persist_audit_log, persist_evidence_links
from crm.ai.repository import persist_suggestions
from crm.ai.schemas import PanelContext, SuggestionResponse
from crm.ai.suggestions import build_suggestion_cards


def build_panel_context(
	reference_doctype: str, reference_name: str, context_type: str = "deal_panel"
) -> PanelContext:
	context = build_base_panel_context(reference_doctype, reference_name, context_type=context_type)
	context["metadata"]["service"] = "crm.ai.service"
	return context


def generate_suggestions(
	reference_doctype: str,
	reference_name: str,
	channel: str | None = None,
	prompt: str | None = None,
	context_type: str = "deal_panel",
) -> SuggestionResponse:
	panel_context = build_panel_context(reference_doctype, reference_name, context_type=context_type)
	agent_request = build_agent_request(panel_context, prompt=prompt, channel=channel)
	runtime_result = execute_agent_request(agent_request)
	job = build_job_stub(reference_doctype, reference_name)
	approval = build_approval_request(reference_doctype, reference_name, channel=channel)
	evidence = build_evidence_packet(panel_context)
	if runtime_result.get("status") != "succeeded":
		audit = build_audit_record(
			reference_doctype,
			reference_name,
			"generate_suggestions",
			"Failed",
			source_type="ai_service",
			source_ref=job["job_id"],
			provider=agent_request.get("provider"),
			job_id=job["job_id"],
			risk_level="High",
			message="Runtime execution failed before suggestion generation.",
			payload={
				"channel": channel,
				"context_type": context_type,
				"runtime_status": runtime_result.get("status"),
				"runtime_mode": runtime_result.get("mode"),
				"runtime_error": runtime_result.get("error"),
			},
		)
		stored_audit = persist_audit_log(audit)
		return {
			"status": "failed",
			"reference": panel_context["reference"],
			"job": job,
			"agent_request": agent_request,
			"approval": approval,
			"runtime": runtime_result,
			"evidence": evidence,
			"suggestions": [],
			"suggestion_ids": [],
			"audit_id": stored_audit["name"],
			"evidence_ids": [],
			"audit": stored_audit,
			"error": runtime_result.get("error"),
		}
	suggestions = build_suggestion_cards(reference_doctype, reference_name, channel=channel)
	stored_suggestions = persist_suggestions(
		reference_doctype,
		reference_name,
		suggestions,
		agent_request,
		evidence,
	)
	evidence_links = build_evidence_links(evidence, channel=channel)
	stored_evidence_links = persist_evidence_links(
		reference_doctype, reference_name, evidence_links, channel=channel
	)
	audit = build_audit_record(
		reference_doctype,
		reference_name,
		"generate_suggestions",
		"Drafted",
		source_type="ai_service",
		source_ref=job["job_id"],
		provider=agent_request.get("provider"),
		job_id=job["job_id"],
		risk_level="Medium" if approval.get("required") else "Low",
		message="Generated draft suggestions for manual review.",
		payload={
			"channel": channel,
			"context_type": context_type,
			"suggestion_count": len(stored_suggestions),
			"runtime_status": runtime_result.get("status"),
			"runtime_attempts": runtime_result.get("attempts"),
		},
	)
	stored_audit = persist_audit_log(audit)

	return {
		"status": "drafted",
		"reference": panel_context["reference"],
		"job": job,
		"agent_request": agent_request,
		"approval": approval,
		"runtime": runtime_result,
		"evidence": evidence,
		"suggestions": suggestions,
		"suggestion_ids": [suggestion["name"] for suggestion in stored_suggestions],
		"audit_id": stored_audit["name"],
		"evidence_ids": [item["name"] for item in stored_evidence_links],
		"audit": stored_audit,
	}
