from __future__ import annotations

import frappe

from crm.ai.agent_client import build_agent_request, check_runtime_health, execute_agent_request
from crm.ai.service import build_panel_context


@frappe.whitelist()
def get_runtime_status() -> dict:
	return check_runtime_health()


@frappe.whitelist()
def run_runtime_smoke_test(
	reference_doctype: str = "CRM Lead",
	reference_name: str = "LEAD-RUNTIME-SMOKE",
	channel: str = "email",
	prompt: str | None = None,
	context_type: str = "deal_panel",
) -> dict:
	panel_context = build_panel_context(reference_doctype, reference_name, context_type=context_type)
	agent_request = build_agent_request(
		panel_context,
		channel=channel,
		prompt=prompt or "OpenClaw runtime smoke test from CRM.",
	)
	runtime = execute_agent_request(agent_request, max_retries=1)
	return {
		"status": runtime.get("status"),
		"health": check_runtime_health(),
		"runtime": runtime,
		"agent_request": agent_request,
		"reference": panel_context["reference"],
	}

