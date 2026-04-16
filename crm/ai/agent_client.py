from __future__ import annotations

import uuid

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


def _is_retryable_error(exc: Exception) -> bool:
	message = str(exc).lower()
	return any(keyword in message for keyword in ("timeout", "temporarily", "rate limit", "retry"))


def _simulate_runtime_response(agent_request: dict[str, object]) -> dict[str, object]:
	prompt = str(agent_request.get("prompt") or "")
	if "[force_retryable_error]" in prompt:
		raise RuntimeError("temporarily unavailable: retry")
	if "[force_fatal_error]" in prompt:
		raise ValueError("invalid request payload")

	return {
		"run_id": f"run-{uuid.uuid4().hex[:10]}",
		"provider": agent_request.get("provider"),
		"status": "succeeded",
		"result": {
			"summary": "Runtime skeleton executed successfully.",
			"suggested_actions": 3,
		},
	}


def execute_agent_request(
	agent_request: dict[str, object],
	max_retries: int = 2,
) -> dict[str, object]:
	attempts = 0
	last_error: str | None = None

	while attempts <= max_retries:
		attempts += 1
		try:
			response = _simulate_runtime_response(agent_request)
			return {
				"status": "succeeded",
				"attempts": attempts,
				"max_retries": max_retries,
				"response": response,
			}
		except Exception as exc:  # pragma: no cover - error path is deterministic in tests
			last_error = str(exc)
			if not _is_retryable_error(exc) or attempts > max_retries:
				return {
					"status": "failed",
					"attempts": attempts,
					"max_retries": max_retries,
					"error": {
						"type": type(exc).__name__,
						"message": last_error,
						"retryable": _is_retryable_error(exc),
					},
				}

	return {
		"status": "failed",
		"attempts": attempts,
		"max_retries": max_retries,
		"error": {"type": "RuntimeError", "message": last_error or "unknown", "retryable": False},
	}
