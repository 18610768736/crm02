from __future__ import annotations

import json
import os
import uuid
from urllib import error, request
from urllib.parse import urlparse, urlunparse

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


def _as_bool(value: str | None, default: bool = False) -> bool:
	if value is None:
		return default
	return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _runtime_required() -> bool:
	return _as_bool(os.getenv("OPENCLAW_RUNTIME_REQUIRED"))


def _allow_simulation_fallback() -> bool:
	return _as_bool(os.getenv("OPENCLAW_RUNTIME_ALLOW_SIMULATION_FALLBACK"), default=True)


def _runtime_health_url(runtime_url: str | None) -> str | None:
	explicit_health_url = os.getenv("OPENCLAW_RUNTIME_HEALTH_URL")
	if explicit_health_url:
		return explicit_health_url
	if not runtime_url:
		return None
	parsed = urlparse(runtime_url)
	path = (parsed.path or "").rstrip("/")
	if not path:
		health_path = "/health"
	elif path.endswith("/health"):
		health_path = path
	else:
		segments = [segment for segment in path.split("/") if segment]
		if not segments:
			health_path = "/health"
		elif segments[-1] in {"runs", "run", "execute", "invoke", "chat", "completions", "responses"}:
			prefix = "/" + "/".join(segments[:-1]) if segments[:-1] else ""
			health_path = f"{prefix}/health" if prefix else "/health"
		else:
			health_path = f"/{'/'.join(segments)}/health"
	return urlunparse((parsed.scheme, parsed.netloc, health_path, "", "", ""))


def _build_runtime_headers() -> dict[str, str]:
	headers = {"Content-Type": "application/json"}
	runtime_token = os.getenv("OPENCLAW_RUNTIME_TOKEN")
	if runtime_token:
		headers["Authorization"] = f"Bearer {runtime_token}"
	return headers


def check_runtime_health(runtime_url: str | None = None) -> dict[str, object]:
	target_runtime_url = runtime_url or os.getenv("OPENCLAW_RUNTIME_URL")
	required = _runtime_required()
	health_url = _runtime_health_url(target_runtime_url)
	result: dict[str, object] = {
		"required": required,
		"runtime_url": target_runtime_url,
		"health_url": health_url,
		"configured": bool(target_runtime_url),
		"healthy": False,
	}

	if not target_runtime_url:
		result["reason"] = "missing_runtime_url"
		result["mode"] = "required" if required else "simulation"
		return result

	if not health_url:
		result["reason"] = "missing_health_url"
		return result

	req = request.Request(health_url, headers=_build_runtime_headers(), method="GET")
	try:
		with request.urlopen(req, timeout=5) as response:  # noqa: S310 - runtime URL is env-configured
			status_code = getattr(response, "status", None) or response.getcode()
			body = response.read().decode("utf-8")
	except error.HTTPError as exc:  # pragma: no cover - network path tested in integration
		result["reason"] = "http_error"
		result["error"] = f"runtime health http error {exc.code}"
		return result
	except error.URLError as exc:  # pragma: no cover - network path tested in integration
		result["reason"] = "unreachable"
		result["error"] = f"runtime health unreachable: {exc.reason}"
		return result

	payload: dict[str, object]
	try:
		payload = json.loads(body) if body else {}
	except json.JSONDecodeError:
		payload = {"raw": body}

	explicit_healthy = payload.get("healthy")
	status_text = str(payload.get("status") or "").lower()
	is_healthy = bool(explicit_healthy) if explicit_healthy is not None else status_text in {
		"",
		"ok",
		"ready",
		"healthy",
	}
	result.update(
		{
			"healthy": bool(status_code and 200 <= int(status_code) < 300 and is_healthy),
			"status_code": status_code,
			"payload": payload,
			"reason": "ok" if bool(status_code and 200 <= int(status_code) < 300 and is_healthy) else "unhealthy",
			"mode": "openclaw_http",
		}
	)
	return result


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
	headers = _build_runtime_headers()

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
	required = _runtime_required()
	if required and not runtime_url:
		return {
			"status": "failed",
			"attempts": 0,
			"max_retries": max_retries,
			"mode": "required_runtime_missing",
			"error": {
				"type": "RuntimeConfigurationError",
				"message": "OPENCLAW_RUNTIME_REQUIRED is enabled but OPENCLAW_RUNTIME_URL is not set.",
				"retryable": False,
			},
		}

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
				if runtime_url and not required and _allow_simulation_fallback():
					response = _simulate_runtime_response(agent_request)
					return {
						"status": "succeeded",
						"attempts": attempts,
						"max_retries": max_retries,
						"mode": "simulation_fallback",
						"response": response,
						"fallback_reason": last_error,
					}
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
