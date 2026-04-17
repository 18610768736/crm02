from __future__ import annotations

import json
import os
import uuid
from urllib import error, request
from urllib.parse import urlparse, urlunparse

from crm import __version__ as CRM_VERSION
from crm.ai.schemas import PanelContext

RUNTIME_PROTOCOL_VERSION = "crm-ai-runtime.v1"
REQUIRED_RUNTIME_CAPABILITIES = ("context_grounding", "draft_generation", "audit_logging")
TERMINAL_RUNTIME_PATHS = {"runs", "run", "execute", "invoke", "chat", "completions", "responses"}


def get_agent_capabilities() -> dict[str, object]:
	return {
		"provider": "clawx",
		"mode": "crm_copilot",
		"client_version": CRM_VERSION,
		"protocol_version": RUNTIME_PROTOCOL_VERSION,
		"features": ["context_grounding", "draft_generation", "audit_logging"],
		"required_runtime_capabilities": list(REQUIRED_RUNTIME_CAPABILITIES),
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
	return _runtime_mode() in {"required", "production"}


def _allow_simulation_fallback() -> bool:
	if _runtime_mode() == "production":
		return False
	return _as_bool(os.getenv("OPENCLAW_RUNTIME_ALLOW_SIMULATION_FALLBACK"), default=True)


def _runtime_mode() -> str:
	configured_mode = str(os.getenv("OPENCLAW_RUNTIME_MODE") or "").strip().lower()
	if configured_mode in {"simulation", "required", "production"}:
		return configured_mode
	if _as_bool(os.getenv("OPENCLAW_RUNTIME_REQUIRED")):
		return "required"
	return "simulation"


def _derive_runtime_endpoint_url(
	runtime_url: str | None,
	endpoint_name: str,
	explicit_env_var: str,
) -> str | None:
	explicit_url = os.getenv(explicit_env_var)
	if explicit_url:
		return explicit_url
	if not runtime_url:
		return None
	parsed = urlparse(runtime_url)
	path = (parsed.path or "").rstrip("/")
	if not path:
		endpoint_path = f"/{endpoint_name}"
	elif path.endswith(f"/{endpoint_name}"):
		endpoint_path = path
	else:
		segments = [segment for segment in path.split("/") if segment]
		if not segments:
			endpoint_path = f"/{endpoint_name}"
		elif segments[-1] in TERMINAL_RUNTIME_PATHS:
			prefix = "/" + "/".join(segments[:-1]) if segments[:-1] else ""
			endpoint_path = f"{prefix}/{endpoint_name}" if prefix else f"/{endpoint_name}"
		else:
			endpoint_path = f"/{'/'.join(segments)}/{endpoint_name}"
	return urlunparse((parsed.scheme, parsed.netloc, endpoint_path, "", "", ""))


def _runtime_health_url(runtime_url: str | None) -> str | None:
	return _derive_runtime_endpoint_url(runtime_url, "health", "OPENCLAW_RUNTIME_HEALTH_URL")


def _runtime_handshake_url(runtime_url: str | None) -> str | None:
	return _derive_runtime_endpoint_url(runtime_url, "handshake", "OPENCLAW_RUNTIME_HANDSHAKE_URL")


def _build_runtime_headers() -> dict[str, str]:
	headers = {"Content-Type": "application/json"}
	runtime_token = os.getenv("OPENCLAW_RUNTIME_TOKEN")
	if runtime_token:
		headers["Authorization"] = f"Bearer {runtime_token}"
	return headers


def _decode_response_body(body: str) -> dict[str, object]:
	try:
		return json.loads(body) if body else {}
	except json.JSONDecodeError:
		return {"raw": body}


def _status_is_ok(status_code: int | None) -> bool:
	return bool(status_code and 200 <= int(status_code) < 300)


def _base_runtime_status(runtime_url: str | None) -> dict[str, object]:
	return {
		"mode": _runtime_mode(),
		"required": _runtime_required(),
		"runtime_url": runtime_url,
		"configured": bool(runtime_url),
	}


def _build_handshake_result(runtime_url: str | None) -> dict[str, object]:
	result = _base_runtime_status(runtime_url)
	result.update(
		{
			"handshake_url": _runtime_handshake_url(runtime_url),
			"compatible": False,
			"version_ok": False,
			"capabilities_ok": False,
			"expected_protocol_version": RUNTIME_PROTOCOL_VERSION,
			"runtime_protocol_version": None,
			"runtime_version": None,
			"required_capabilities": list(REQUIRED_RUNTIME_CAPABILITIES),
			"missing_capabilities": list(REQUIRED_RUNTIME_CAPABILITIES),
		}
	)
	return result


def _extract_runtime_capabilities(payload: dict[str, object]) -> list[str]:
	raw_capabilities = payload.get("capabilities") or payload.get("features") or []
	if isinstance(raw_capabilities, str):
		return [raw_capabilities]
	if isinstance(raw_capabilities, (list, tuple, set)):
		return [str(item) for item in raw_capabilities if item]
	return []


def check_runtime_health(runtime_url: str | None = None) -> dict[str, object]:
	target_runtime_url = runtime_url or os.getenv("OPENCLAW_RUNTIME_URL")
	health_url = _runtime_health_url(target_runtime_url)
	result = _base_runtime_status(target_runtime_url)
	result.update({"health_url": health_url, "healthy": False})

	if not target_runtime_url:
		result["reason"] = "missing_runtime_url"
		result["error"] = {
			"type": "RuntimeConfigurationError",
			"message": "OPENCLAW_RUNTIME_URL is not configured.",
		}
		return result

	if not health_url:
		result["reason"] = "missing_health_url"
		result["error"] = {
			"type": "RuntimeConfigurationError",
			"message": "Unable to derive runtime health URL.",
		}
		return result

	req = request.Request(health_url, headers=_build_runtime_headers(), method="GET")
	try:
		with request.urlopen(req, timeout=5) as response:  # noqa: S310 - runtime URL is env-configured
			status_code = getattr(response, "status", None) or response.getcode()
			body = response.read().decode("utf-8")
	except error.HTTPError as exc:  # pragma: no cover - network path tested in integration
		body = exc.read().decode("utf-8") if exc.fp else ""
		payload = _decode_response_body(body)
		result["reason"] = "http_error"
		result["status_code"] = exc.code
		result["payload"] = payload
		result["error"] = {
			"type": "RuntimeHealthHTTPError",
			"message": f"runtime health http error {exc.code}",
		}
		return result
	except error.URLError as exc:  # pragma: no cover - network path tested in integration
		result["reason"] = "unreachable"
		result["error"] = {
			"type": "RuntimeHealthConnectionError",
			"message": f"runtime health unreachable: {exc.reason}",
		}
		return result

	payload = _decode_response_body(body)

	explicit_healthy = payload.get("healthy")
	status_text = str(payload.get("status") or "").lower()
	is_healthy = bool(explicit_healthy) if explicit_healthy is not None else status_text in {
		"",
		"ok",
		"ready",
		"healthy",
	}
	healthy = bool(_status_is_ok(status_code) and is_healthy)
	result.update(
		{
			"healthy": healthy,
			"status_code": status_code,
			"payload": payload,
			"reason": "ok" if healthy else "unhealthy",
			"mode": "openclaw_http",
		}
	)
	return result


def check_runtime_handshake(runtime_url: str | None = None) -> dict[str, object]:
	target_runtime_url = runtime_url or os.getenv("OPENCLAW_RUNTIME_URL")
	result = _build_handshake_result(target_runtime_url)
	handshake_url = result["handshake_url"]

	if not target_runtime_url:
		result["reason"] = "missing_runtime_url"
		result["error"] = {
			"type": "RuntimeConfigurationError",
			"message": "OPENCLAW_RUNTIME_URL is not configured.",
		}
		return result

	if not handshake_url:
		result["reason"] = "missing_handshake_url"
		result["error"] = {
			"type": "RuntimeConfigurationError",
			"message": "Unable to derive runtime handshake URL.",
		}
		return result

	req = request.Request(handshake_url, headers=_build_runtime_headers(), method="GET")
	try:
		with request.urlopen(req, timeout=5) as response:  # noqa: S310 - runtime URL is env-configured
			status_code = getattr(response, "status", None) or response.getcode()
			body = response.read().decode("utf-8")
	except error.HTTPError as exc:  # pragma: no cover - network path tested in integration
		body = exc.read().decode("utf-8") if exc.fp else ""
		payload = _decode_response_body(body)
		result.update(
			{
				"reason": "http_error",
				"status_code": exc.code,
				"payload": payload,
				"error": {
					"type": "RuntimeHandshakeHTTPError",
					"message": f"runtime handshake http error {exc.code}",
				},
			}
		)
		return result
	except error.URLError as exc:  # pragma: no cover - network path tested in integration
		result.update(
			{
				"reason": "unreachable",
				"error": {
					"type": "RuntimeHandshakeConnectionError",
					"message": f"runtime handshake unreachable: {exc.reason}",
				},
			}
		)
		return result

	payload = _decode_response_body(body)
	runtime_protocol_version = str(payload.get("protocol_version") or "").strip() or None
	runtime_capabilities = _extract_runtime_capabilities(payload)
	missing_capabilities = [
		capability
		for capability in REQUIRED_RUNTIME_CAPABILITIES
		if capability not in set(runtime_capabilities)
	]
	version_ok = runtime_protocol_version == RUNTIME_PROTOCOL_VERSION
	capabilities_ok = not missing_capabilities
	compatible = _status_is_ok(status_code) and version_ok and capabilities_ok
	reason = "ok"
	if not version_ok:
		reason = "version_mismatch"
	elif not capabilities_ok:
		reason = "missing_capabilities"

	result.update(
		{
			"status_code": status_code,
			"payload": payload,
			"runtime_protocol_version": runtime_protocol_version,
			"runtime_version": payload.get("runtime_version"),
			"capabilities": runtime_capabilities,
			"missing_capabilities": missing_capabilities,
			"version_ok": version_ok,
			"capabilities_ok": capabilities_ok,
			"compatible": compatible,
			"reason": reason,
			"mode": "openclaw_http",
		}
	)
	return result


def check_runtime_readiness(runtime_url: str | None = None) -> dict[str, object]:
	target_runtime_url = runtime_url or os.getenv("OPENCLAW_RUNTIME_URL")
	health = check_runtime_health(target_runtime_url)
	if health.get("healthy"):
		handshake = check_runtime_handshake(target_runtime_url)
	else:
		handshake = _build_handshake_result(target_runtime_url)
		handshake["reason"] = "skipped_unhealthy_runtime"

	return {
		**_base_runtime_status(target_runtime_url),
		"ready": bool(health.get("healthy") and handshake.get("compatible")),
		"health": health,
		"handshake": handshake,
	}


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
	runtime_mode = _runtime_mode()
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

	readiness: dict[str, object] | None = None
	if runtime_mode == "production":
		readiness = check_runtime_readiness(runtime_url)
		if not readiness.get("ready"):
			return {
				"status": "failed",
				"attempts": 0,
				"max_retries": max_retries,
				"mode": "production_readiness_failed",
				"readiness": readiness,
				"error": {
					"type": "RuntimeReadinessError",
					"message": (
						"runtime readiness check failed: "
						f"health={readiness['health'].get('reason')}, "
						f"handshake={readiness['handshake'].get('reason')}"
					),
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
				"readiness": readiness,
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
