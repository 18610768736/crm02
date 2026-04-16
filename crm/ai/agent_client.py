from __future__ import annotations

import json
import os
import uuid
from urllib import error, request

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


def _execute_via_openclaw_runtime(
	runtime_url: str,
	agent_request: dict[str, object],
) -> dict[str, object]:
	payload = json.dumps(agent_request).encode("utf-8")
	headers = {"Content-Type": "application/json"}
	runtime_token = os.getenv("OPENCLAW_RUNTIME_TOKEN")
	if runtime_token:
		headers["Authorization"] = f"Bearer {runtime_token}"

	req = request.Request(runtime_url, data=payload, headers=headers, method="POST")
	try:
		with request.urlopen(req, timeout=10) as response:  # noqa: S310 - runtime URL is env-configured
			body = response.read().decode("utf-8")
	except error.HTTPError as exc:  # pragma: no cover - network path tested in integration
		body = exc.read().decode("utf-8") if exc.fp else ""
		raise RuntimeError(f"runtime http error {exc.code}: {body}") from exc
	except error.URLError as exc:  # pragma: no cover - network path tested in integration
		raise RuntimeError(f"runtime unreachable: {exc.reason}") from exc

	try:
		response_data = json.loads(body) if body else {}
	except json.JSONDecodeError:
		response_data = {"raw": body}

	return {
		"run_id": response_data.get("run_id") or f"run-{uuid.uuid4().hex[:10]}",
		"provider": "openclaw_runtime",
		"status": response_data.get("status") or "succeeded",
		"result": response_data.get("result") or response_data,
	}


def execute_agent_request(
	agent_request: dict[str, object],
	max_retries: int = 2,
) -> dict[str, object]:
	runtime_url = os.getenv("OPENCLAW_RUNTIME_URL")
	attempts = 0
	last_error: str | None = None

	while attempts <= max_retries:
		attempts += 1
		try:
			if runtime_url:
				response = _execute_via_openclaw_runtime(runtime_url, agent_request)
			else:
				response = _simulate_runtime_response(agent_request)
			return {
				"status": "succeeded",
				"attempts": attempts,
				"max_retries": max_retries,
				"mode": "openclaw_http" if runtime_url else "simulation",
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
