from __future__ import annotations

from crm.ai.schemas import PanelContext


def get_agent_capabilities() -> dict[str, object]:
	return {
		"provider": "clawx",
		"mode": "crm_copilot",
		"features": ["context_grounding", "draft_generation", "audit_logging"],
		"human_in_the_loop": True,
	}


def build_agent_request(
	context: PanelContext, prompt: str | None = None, channel: str | None = None
) -> dict[str, object]:
	target_channel = channel or "email"
	reference = context["reference"]
	default_prompt = (
		f"Generate the next best action for {reference['doctype']} {reference['name']} "
		f"on channel {target_channel}."
	)

	return {
		"provider": "clawx",
		"mode": "crm_copilot",
		"channel": target_channel,
		"prompt": prompt or default_prompt,
		"context_type": context["context_type"],
		"reference": reference,
		"capabilities": get_agent_capabilities(),
	}
