from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from typing import Any

try:
	import frappe
except ModuleNotFoundError:  # pragma: no cover - local non-Frappe environments
	frappe = None

_VOLATILE_NONCE_CACHE: dict[str, int] = {}
_DEFAULT_WINDOW_SECONDS = 300


def _as_bool(value: Any, default: bool = False) -> bool:
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int) -> int:
	if value is None:
		return default
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def _channel_suffix(channel: str) -> str:
	return str(channel or "").strip().upper()


def _get_secret(channel: str) -> str | None:
	suffix = _channel_suffix(channel)
	candidates = [
		f"CRM_CHANNEL_SYNC_SECRET_{suffix}",
		f"CRM_CHANNEL_SYNC_WEBHOOK_SECRET_{suffix}",
		"CRM_CHANNEL_SYNC_SECRET",
		"CRM_CHANNEL_SYNC_WEBHOOK_SECRET",
	]
	for key in candidates:
		value = os.getenv(key)
		if value:
			return value
	return None


def _is_enforced(channel: str, verify_signature: bool | None) -> bool:
	if verify_signature is not None:
		return bool(verify_signature)

	suffix = _channel_suffix(channel)
	per_channel_flag = os.getenv(f"CRM_CHANNEL_SYNC_ENFORCE_SIGNATURE_{suffix}")
	global_flag = os.getenv("CRM_CHANNEL_SYNC_ENFORCE_SIGNATURE")
	return _as_bool(per_channel_flag) or _as_bool(global_flag)


def _window_seconds(channel: str) -> int:
	suffix = _channel_suffix(channel)
	per_channel_window = os.getenv(f"CRM_CHANNEL_SYNC_SIGNATURE_WINDOW_SECONDS_{suffix}")
	global_window = os.getenv("CRM_CHANNEL_SYNC_SIGNATURE_WINDOW_SECONDS")
	if per_channel_window:
		return max(30, _as_int(per_channel_window, _DEFAULT_WINDOW_SECONDS))
	if global_window:
		return max(30, _as_int(global_window, _DEFAULT_WINDOW_SECONDS))
	return _DEFAULT_WINDOW_SECONDS


def _normalize_signature(signature: str | None) -> str | None:
	if not signature:
		return None
	value = str(signature).strip()
	if "=" in value:
		prefix, digest = value.split("=", 1)
		if prefix.lower() in {"sha256", "hmac-sha256"}:
			return digest.strip()
	return value


def _request_headers() -> dict[str, str]:
	if not frappe:
		return {}
	request = getattr(getattr(frappe, "local", None), "request", None)
	if not request:
		return {}
	return {str(key).lower(): str(value) for key, value in request.headers.items()}


def extract_webhook_auth(
	payload: dict[str, Any],
	signature: str | None = None,
	timestamp: str | int | None = None,
	nonce: str | None = None,
) -> tuple[str | None, str | None, str | None]:
	resolved_signature = signature or payload.get("signature") or payload.get("webhook_signature")
	resolved_timestamp = timestamp or payload.get("timestamp") or payload.get("ts")
	resolved_nonce = nonce or payload.get("nonce") or payload.get("request_id")

	headers = _request_headers()
	if not resolved_signature:
		for key in (
			"x-signature",
			"x-webhook-signature",
			"x-lark-signature",
			"x-qywx-signature",
		):
			if headers.get(key):
				resolved_signature = headers[key]
				break
	if not resolved_timestamp:
		for key in (
			"x-timestamp",
			"x-request-timestamp",
			"x-lark-request-timestamp",
			"x-qywx-timestamp",
		):
			if headers.get(key):
				resolved_timestamp = headers[key]
				break
	if not resolved_nonce:
		for key in (
			"x-nonce",
			"x-request-nonce",
			"x-lark-request-nonce",
			"x-qywx-nonce",
		):
			if headers.get(key):
				resolved_nonce = headers[key]
				break

	timestamp_text = str(resolved_timestamp).strip() if resolved_timestamp is not None else None
	nonce_text = str(resolved_nonce).strip() if resolved_nonce is not None else None
	signature_text = str(resolved_signature).strip() if resolved_signature else None
	return signature_text, timestamp_text, nonce_text


def build_webhook_signature(
	secret: str,
	raw_payload: str,
	timestamp: str | int,
	nonce: str,
) -> str:
	message = f"{timestamp}.{nonce}.{raw_payload}".encode("utf-8")
	return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _nonce_cache_key(channel: str, timestamp: int, nonce: str) -> str:
	return f"crm:channel-sync:nonce:{channel}:{timestamp}:{nonce}"


def _is_replay(channel: str, timestamp: int, nonce: str) -> bool:
	key = _nonce_cache_key(channel, timestamp, nonce)
	if frappe:
		cache = frappe.cache()
		return bool(cache.get_value(key))
	return key in _VOLATILE_NONCE_CACHE and _VOLATILE_NONCE_CACHE[key] > int(time.time())


def _remember_nonce(channel: str, timestamp: int, nonce: str, ttl_seconds: int) -> None:
	key = _nonce_cache_key(channel, timestamp, nonce)
	if frappe:
		cache = frappe.cache()
		cache.set_value(key, "1", expires_in_sec=ttl_seconds)
		return
	_VOLATILE_NONCE_CACHE[key] = int(time.time()) + ttl_seconds


def _gc_nonce_cache(now_ts: int) -> None:
	expired = [key for key, expires_at in _VOLATILE_NONCE_CACHE.items() if expires_at <= now_ts]
	for key in expired:
		_VOLATILE_NONCE_CACHE.pop(key, None)


def verify_webhook_request(
	channel: str,
	raw_payload: str,
	payload: dict[str, Any],
	signature: str | None = None,
	timestamp: str | int | None = None,
	nonce: str | None = None,
	verify_signature: bool | None = None,
	now_ts: int | None = None,
) -> dict[str, Any]:
	enforced = _is_enforced(channel, verify_signature)
	secret = _get_secret(channel)
	window_seconds = _window_seconds(channel)
	now_timestamp = int(now_ts or time.time())
	_gc_nonce_cache(now_timestamp)

	resolved_signature, resolved_timestamp, resolved_nonce = extract_webhook_auth(
		payload,
		signature=signature,
		timestamp=timestamp,
		nonce=nonce,
	)
	base_result = {
		"required": enforced,
		"verified": False,
		"mode": "enforced" if enforced else "optional",
		"timestamp": resolved_timestamp,
		"nonce": resolved_nonce,
	}

	if not enforced:
		base_result.update(
			{
				"verified": bool(secret and resolved_signature and resolved_timestamp and resolved_nonce),
				"reason": "verification_optional",
			}
		)
		return base_result

	if not secret:
		return {**base_result, "reason": "missing_secret", "error": "Missing webhook secret."}

	if not resolved_signature or not resolved_timestamp or not resolved_nonce:
		return {
			**base_result,
			"reason": "missing_headers",
			"error": "Missing webhook signature, timestamp, or nonce.",
		}

	timestamp_value = _as_int(resolved_timestamp, default=0)
	if timestamp_value <= 0:
		return {**base_result, "reason": "invalid_timestamp", "error": "Invalid webhook timestamp."}

	if abs(now_timestamp - timestamp_value) > window_seconds:
		return {
			**base_result,
			"reason": "timestamp_out_of_window",
			"error": "Webhook timestamp is outside the allowed verification window.",
		}

	if _is_replay(channel, timestamp_value, resolved_nonce):
		return {**base_result, "reason": "replay_detected", "error": "Webhook nonce replay detected."}

	expected_signature = build_webhook_signature(secret, raw_payload, timestamp_value, resolved_nonce)
	if not hmac.compare_digest(
		_normalize_signature(resolved_signature) or "",
		_normalize_signature(expected_signature) or "",
	):
		return {**base_result, "reason": "signature_mismatch", "error": "Invalid webhook signature."}

	_remember_nonce(channel, timestamp_value, resolved_nonce, window_seconds)
	request_id = f"sig-{uuid.uuid4().hex[:12]}"
	return {
		**base_result,
		"verified": True,
		"reason": "ok",
		"request_id": request_id,
	}


def reset_webhook_security_state() -> None:
	_VOLATILE_NONCE_CACHE.clear()
