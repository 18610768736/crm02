from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urljoin

import requests


def _coerce_dict(value: dict[str, Any] | str | None) -> dict[str, Any]:
	if isinstance(value, dict):
		return dict(value)
	if isinstance(value, str) and value.strip():
		return json.loads(value)
	return {}


def _coerce_bool(value: Any, default: bool = True) -> bool:
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_int(value: Any, default: int) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def _deep_get(payload: Any, path: str | None) -> Any:
	if not path:
		return None
	current = payload
	for segment in str(path).split("."):
		if isinstance(current, dict):
			current = current.get(segment)
			continue
		if isinstance(current, list):
			try:
				current = current[int(segment)]
			except (TypeError, ValueError, IndexError):
				return None
			continue
		return None
	return current


def _resolve_first(payload: Any, candidates: list[str | None]) -> Any:
	for candidate in candidates:
		if not candidate:
			continue
		value = _deep_get(payload, candidate)
		if value is not None:
			return value
	return None


def _resolve_endpoint_url(
	credential: dict[str, Any],
	metadata: dict[str, Any],
	purpose: str,
) -> str:
	direct_url = metadata.get(f"{purpose}_url") or metadata.get("http_url")
	if direct_url:
		return str(direct_url)

	base_url = str(
		metadata.get("base_url")
		or credential.get("base_url")
		or ""
	).strip()
	path = str(
		metadata.get(f"{purpose}_path")
		or metadata.get("http_path")
		or ""
	).strip()
	if not base_url and not path:
		raise ValueError(f"Missing configured {purpose} endpoint.")
	if not base_url:
		return path
	if not path:
		return base_url
	return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _build_auth(
	credential: dict[str, Any],
	metadata: dict[str, Any],
	headers: dict[str, Any],
	params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
	auth_type = str(credential.get("auth_type") or "Bearer Token").strip().lower()
	access_token = credential.get("access_token")
	refresh_token = credential.get("refresh_token")
	resolved_headers = dict(headers)
	resolved_params = dict(params)

	if auth_type in {"bearer token", "oauth2"}:
		if access_token:
			resolved_headers.setdefault("Authorization", f"Bearer {access_token}")
	elif auth_type == "api key":
		api_key_location = str(metadata.get("api_key_location") or "header").strip().lower()
		api_key_name = str(metadata.get("api_key_name") or "X-API-Key").strip()
		if access_token:
			if api_key_location == "query":
				resolved_params.setdefault(api_key_name, access_token)
			else:
				resolved_headers.setdefault(api_key_name, access_token)
	elif auth_type == "basic":
		if access_token or refresh_token:
			pair = f"{access_token or ''}:{refresh_token or ''}".encode("utf-8")
			digest = base64.b64encode(pair).decode("utf-8")
			resolved_headers.setdefault("Authorization", f"Basic {digest}")

	return resolved_headers, resolved_params


def _request_json(
	credential: dict[str, Any],
	metadata: dict[str, Any],
	cursor: dict[str, Any] | None,
	limit: int,
	purpose: str,
) -> dict[str, Any]:
	method = str(
		metadata.get(f"{purpose}_http_method")
		or metadata.get("http_method")
		or "GET"
	).strip().upper()
	url = _resolve_endpoint_url(credential, metadata, purpose)
	timeout = max(1, _coerce_int(metadata.get("timeout_seconds"), 10))
	verify_ssl = _coerce_bool(metadata.get("verify_ssl"), default=True)

	params = {
		**_coerce_dict(metadata.get("query_params")),
		**_coerce_dict(metadata.get(f"{purpose}_query_params")),
	}
	body = {
		**_coerce_dict(metadata.get("request_body")),
		**_coerce_dict(metadata.get(f"{purpose}_request_body")),
	}
	headers = {
		"Accept": "application/json",
		**_coerce_dict(metadata.get("http_headers")),
		**_coerce_dict(metadata.get(f"{purpose}_headers")),
	}

	cursor_key = str((cursor or {}).get("cursor_key") or "")
	cursor_value = (cursor or {}).get("cursor_value")
	cursor_key_param = metadata.get("cursor_key_param")
	cursor_value_param = metadata.get("cursor_value_param") or metadata.get("cursor_param") or "cursor"
	limit_param = metadata.get("limit_param") or "limit"

	cursor_location = str(metadata.get("cursor_location") or "query").strip().lower()
	limit_location = str(metadata.get("limit_location") or cursor_location).strip().lower()

	if cursor_key and cursor_key_param:
		if cursor_location == "body":
			body.setdefault(str(cursor_key_param), cursor_key)
		else:
			params.setdefault(str(cursor_key_param), cursor_key)
	if cursor_value is not None and cursor_value_param:
		if cursor_location == "body":
			body.setdefault(str(cursor_value_param), cursor_value)
		else:
			params.setdefault(str(cursor_value_param), cursor_value)
	if limit_param:
		if limit_location == "body":
			body.setdefault(str(limit_param), limit)
		else:
			params.setdefault(str(limit_param), limit)

	headers, params = _build_auth(credential, metadata, headers, params)
	response = requests.request(
		method,
		url,
		headers=headers or None,
		params=params or None,
		json=body or None,
		timeout=timeout,
		verify=verify_ssl,
	)
	response.raise_for_status()
	try:
		payload = response.json() if response.content else {}
	except ValueError as exc:
		raise RuntimeError(f"HTTP connector expected JSON response from {url}") from exc

	return {
		"method": method,
		"url": url,
		"status_code": response.status_code,
		"payload": payload,
	}


def _ensure_event_list(value: Any) -> list[dict[str, Any]]:
	if value is None:
		return []
	if isinstance(value, list):
		return [item for item in value if isinstance(item, dict)]
	if isinstance(value, dict):
		return [value]
	raise RuntimeError("Configured HTTP events payload is not a JSON object/list.")


def _inject_context(
	channel: str,
	credential: dict[str, Any],
	event: dict[str, Any],
	cursor_key: str,
	next_cursor_value: str,
) -> dict[str, Any]:
	metadata = credential.get("metadata") or {}
	credential_key = credential.get("credential_key") or credential.get("name") or "default"
	workspace_key = metadata.get("workspace_key") or f"{channel}::{credential_key}"
	payload = dict(event)
	payload.setdefault("workspace_key", workspace_key)
	payload.setdefault("workspace_name", metadata.get("workspace_name") or workspace_key)
	payload.setdefault("tenant_id", metadata.get("tenant_id"))
	payload.setdefault("account_id", metadata.get("account_id"))
	payload.setdefault("cursor_key", cursor_key)
	payload.setdefault("cursor_value", next_cursor_value)
	return payload


def pull_via_http(
	channel: str,
	credential: dict[str, Any],
	cursor: dict[str, Any] | None = None,
	limit: int = 20,
	default_event_paths: list[str] | None = None,
) -> dict[str, Any]:
	metadata = credential.get("metadata") or {}
	response_info = _request_json(credential, metadata, cursor, limit, purpose="pull")
	response_payload = response_info["payload"]
	default_paths = default_event_paths or []
	raw_events = _resolve_first(
		response_payload,
		[
			metadata.get("events_path"),
			*default_paths,
			"events",
			"items",
			"data.events",
			"data.items",
			"data.messages",
			"messages",
			"records",
		],
	)
	events = _ensure_event_list(raw_events if raw_events is not None else response_payload)
	cursor_key = str(
		_resolve_first(
			response_payload,
			[
				metadata.get("cursor_key_path"),
				"cursor_key",
				"meta.cursor_key",
			],
		)
		or (cursor or {}).get("cursor_key")
		or f"{channel}::{credential.get('credential_key') or credential.get('name') or 'default'}"
	)
	next_cursor_value = _resolve_first(
		response_payload,
		[
			metadata.get("next_cursor_path"),
			"next_cursor",
			"cursor.next",
			"meta.next_cursor",
			"paging.next_cursor",
		],
	)
	if next_cursor_value is None and events:
		next_cursor_value = _resolve_first(
			events[-1],
			[
				metadata.get("event_cursor_field"),
				"cursor_value",
				"event_id",
				"message_id",
				"msgid",
				"id",
				"event_time",
				"sent_at",
				"create_time",
			],
		)
	if next_cursor_value is None:
		next_cursor_value = (cursor or {}).get("cursor_value") or "0"
	next_cursor_value = str(next_cursor_value)

	has_more = _resolve_first(
		response_payload,
		[
			metadata.get("has_more_path"),
			"has_more",
			"meta.has_more",
			"paging.has_more",
		],
	)
	return {
		"events": [
			_inject_context(
				channel,
				credential,
				event,
				cursor_key=cursor_key,
				next_cursor_value=next_cursor_value,
			)
			for event in events
		],
		"cursor_key": cursor_key,
		"next_cursor_value": next_cursor_value,
		"status": "ok",
		"has_more": bool(has_more),
		"mode": "http",
		"http_status_code": response_info["status_code"],
		"request_url": response_info["url"],
	}


def validate_via_http(
	channel: str,
	credential: dict[str, Any],
	limit: int = 1,
	default_event_paths: list[str] | None = None,
) -> dict[str, Any]:
	metadata = credential.get("metadata") or {}
	purpose = "test" if (metadata.get("test_url") or metadata.get("test_path")) else "pull"
	response_info = _request_json(credential, metadata, cursor=None, limit=limit, purpose=purpose)
	response_payload = response_info["payload"]
	default_paths = default_event_paths or []
	raw_events = _resolve_first(
		response_payload,
		[
			metadata.get("events_path"),
			*default_paths,
			"events",
			"items",
			"data.events",
			"data.items",
			"data.messages",
			"messages",
			"records",
		],
	)
	event_count = len(_ensure_event_list(raw_events)) if raw_events is not None else 0
	return {
		"ok": True,
		"channel": channel,
		"mode": "http",
		"status": "connected",
		"event_count": event_count,
		"http_status_code": response_info["status_code"],
		"request_url": response_info["url"],
	}
