from __future__ import annotations

import os
from typing import Any

from crm.channel_syncing.alerts import emit_sync_alert
from crm.channel_syncing.connectors import pull_connector_events
from crm.channel_syncing.repository import (
	get_channel_credential,
	list_channel_credentials,
	upsert_channel_credential,
	upsert_sync_cursor,
)

SUPPORTED_CHANNELS = ("qywx", "lark", "email")


def get_supported_channels() -> list[str]:
	return list(SUPPORTED_CHANNELS)


def _ingest_pulled_event(channel: str, payload: dict[str, Any]) -> dict[str, Any]:
	from crm.api.channel_sync import ingest_event

	return ingest_event(channel, payload, verify_signature=0)


def _is_auth_failure(error_message: str | None) -> bool:
	text = str(error_message or "").lower()
	return any(keyword in text for keyword in ("401", "403", "unauthorized", "invalid token", "invalid credential"))


def _as_int(value: Any, default: int) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def _scheduled_channels_from_env() -> list[str] | None:
	raw_channels = str(os.getenv("CRM_CHANNEL_SYNC_SCHEDULED_CHANNELS") or "").strip()
	if not raw_channels:
		return None
	channels = [item.strip() for item in raw_channels.split(",") if item.strip()]
	return channels or None


def _sync_single_credential(
	channel: str,
	credential: dict[str, Any],
	cursor_key: str | None = None,
	cursor_value: str | None = None,
	limit: int = 20,
	max_retries: int = 1,
) -> dict[str, Any]:
	credential_id = credential["name"]
	credential_key = credential.get("credential_key") or credential_id
	metadata = credential.get("metadata") or {}
	previous_failure_count = int(credential.get("failure_count") or 0)
	target_cursor_key = cursor_key or f"{channel}::{credential_key}"
	target_cursor_value = str(cursor_value or metadata.get("last_cursor_value") or 0)
	attempt = 0
	last_error: str | None = None

	while attempt <= max_retries:
		attempt += 1
		try:
			pull_result = pull_connector_events(
				channel=channel,
				credential=credential,
				cursor={"cursor_key": target_cursor_key, "cursor_value": target_cursor_value},
				limit=limit,
			)
			events = pull_result.get("events") or []
			processed_event_ids: list[str] = []
			for event in events:
				event_payload = dict(event)
				event_payload.setdefault("workspace_key", metadata.get("workspace_key") or f"{channel}::{credential_key}")
				event_payload.setdefault("workspace_name", metadata.get("workspace_name"))
				event_payload.setdefault("tenant_id", metadata.get("tenant_id"))
				event_payload.setdefault("account_id", metadata.get("account_id"))
				event_payload.setdefault("cursor_key", pull_result.get("cursor_key") or target_cursor_key)
				event_payload.setdefault("cursor_value", target_cursor_value)
				ingest_result = _ingest_pulled_event(channel, event_payload)
				processed_event_ids.append(ingest_result["normalized_event"]["external_id"])

			next_cursor_value = str(pull_result.get("next_cursor_value") or target_cursor_value)
			stored_cursor = upsert_sync_cursor(
				channel=channel,
				workspace_id=credential.get("workspace"),
				cursor_key=pull_result.get("cursor_key") or target_cursor_key,
				cursor_value=next_cursor_value,
				status="Succeeded",
				retry_count=max(attempt - 1, 0),
				metadata={
					"mode": "pull_sync",
					"credential_id": credential_id,
					"processed_event_ids": processed_event_ids,
					"event_count": len(processed_event_ids),
					"connector_mode": pull_result.get("mode") or metadata.get("pull_mode") or "mock",
				},
			)
			upsert_channel_credential(
				channel=channel,
				workspace_id=credential.get("workspace"),
				credential_key=credential_key,
				auth_type=credential.get("auth_type"),
				base_url=credential.get("base_url"),
				access_token=credential.get("access_token"),
				refresh_token=credential.get("refresh_token"),
				status=credential.get("status") or "Active",
				expires_at=credential.get("expires_at"),
				metadata={
					**metadata,
					"last_cursor_key": pull_result.get("cursor_key") or target_cursor_key,
					"last_cursor_value": next_cursor_value,
					"last_pull_count": len(processed_event_ids),
					"last_pull_mode": pull_result.get("mode") or metadata.get("pull_mode") or "mock",
					"last_request_url": pull_result.get("request_url"),
					"last_http_status_code": pull_result.get("http_status_code"),
					"last_success_at": stored_cursor.get("last_synced_at"),
					"last_error": None,
					"last_error_kind": None,
				},
				last_validated_at=stored_cursor.get("last_synced_at"),
				failure_count=0,
			)
			if previous_failure_count > 0 or attempt > 1:
				emit_sync_alert(
					channel=channel,
					code="pull_sync_recovered",
					severity="info",
					message=f"Pull sync recovered for credential {credential_key}.",
					context={
						"credential_id": credential_id,
						"cursor_id": stored_cursor["name"],
						"retry_count": max(attempt - 1, 0),
						"event_count": len(processed_event_ids),
					},
				)
			return {
				"channel": channel,
				"credential_id": credential_id,
				"status": "succeeded",
				"cursor_id": stored_cursor["name"],
				"cursor_key": pull_result.get("cursor_key") or target_cursor_key,
				"cursor_value": next_cursor_value,
				"retry_count": max(attempt - 1, 0),
				"event_count": len(processed_event_ids),
				"event_ids": processed_event_ids,
				"connector_mode": pull_result.get("mode") or metadata.get("pull_mode") or "mock",
			}
		except Exception as exc:  # pragma: no cover - defensive fallback
			last_error = str(exc)
			final_failure = attempt > max_retries
			auth_failure = _is_auth_failure(last_error)
			stored_cursor = upsert_sync_cursor(
				channel=channel,
				workspace_id=credential.get("workspace"),
				cursor_key=target_cursor_key,
				cursor_value=target_cursor_value,
				status="Failed" if final_failure else "Retrying",
				retry_count=attempt,
				last_error=last_error,
				metadata={
					"mode": "pull_sync",
					"credential_id": credential_id,
					"attempt": attempt,
					"max_retries": max_retries,
				},
			)
			upsert_channel_credential(
				channel=channel,
				workspace_id=credential.get("workspace"),
				credential_key=credential_key,
				auth_type=credential.get("auth_type"),
				base_url=credential.get("base_url"),
				access_token=credential.get("access_token"),
				refresh_token=credential.get("refresh_token"),
				status=(
					"Invalid"
					if final_failure and auth_failure
					else (credential.get("status") or "Active")
				),
				expires_at=credential.get("expires_at"),
				metadata={
					**metadata,
					"last_cursor_key": target_cursor_key,
					"last_cursor_value": target_cursor_value,
					"last_error": last_error,
					"last_error_kind": "auth" if auth_failure else "operational",
					"last_failure_at": stored_cursor.get("last_synced_at"),
				},
				failure_count=attempt,
			)
			if not final_failure:
				emit_sync_alert(
					channel=channel,
					code="pull_sync_retrying",
					severity="warning",
					message=f"Pull sync retrying for credential {credential_key}: {last_error}",
					context={
						"credential_id": credential_id,
						"cursor_id": stored_cursor["name"],
						"cursor_key": target_cursor_key,
						"attempt": attempt,
						"max_retries": max_retries,
					},
				)
			if final_failure:
				emit_sync_alert(
					channel=channel,
					code="pull_sync_failed",
					severity="error",
					message=f"Pull sync failed for credential {credential_key}: {last_error}",
					context={
						"credential_id": credential_id,
						"cursor_id": stored_cursor["name"],
						"cursor_key": target_cursor_key,
						"attempt": attempt,
					},
				)
				if auth_failure:
					emit_sync_alert(
						channel=channel,
						code="pull_sync_auth_invalid",
						severity="error",
						message=f"Credential {credential_key} marked invalid after auth failure.",
						context={
							"credential_id": credential_id,
							"cursor_id": stored_cursor["name"],
							"cursor_key": target_cursor_key,
						},
					)
				break

	return {
		"channel": channel,
		"credential_id": credential_id,
		"status": "failed",
		"cursor_id": stored_cursor["name"] if "stored_cursor" in locals() else None,
		"cursor_key": target_cursor_key,
		"cursor_value": target_cursor_value,
		"retry_count": max_retries + 1,
		"event_count": 0,
		"message": f"Pull sync failed after retries: {last_error or 'unknown error'}",
	}


def sync_channel(
	channel: str,
	credential_id: str | None = None,
	cursor_key: str | None = None,
	cursor_value: str | None = None,
	limit: int = 20,
	max_retries: int = 1,
) -> dict[str, Any]:
	if channel not in SUPPORTED_CHANNELS:
		raise ValueError(f"Unsupported channel: {channel}")

	credentials: list[dict[str, Any]] = []
	if credential_id:
		credentials = [get_channel_credential(credential_id, include_secrets=True)]
	else:
		credentials = list_channel_credentials(
			channel=channel,
			status="Active",
			limit=100,
			include_secrets=True,
		)

	if not credentials:
		return {
			"channel": channel,
			"status": "skipped",
			"message": "No active channel credentials configured.",
			"results": [],
			"processed_events": 0,
		}

	results = [
		_sync_single_credential(
			channel=channel,
			credential=credential,
			cursor_key=cursor_key,
			cursor_value=cursor_value,
			limit=limit,
			max_retries=max_retries,
		)
		for credential in credentials
	]
	success_count = len([item for item in results if item.get("status") == "succeeded"])
	processed_events = sum(int(item.get("event_count") or 0) for item in results)
	status = "succeeded"
	if success_count == 0:
		status = "failed"
	elif success_count < len(results):
		status = "partial"

	return {
		"channel": channel,
		"status": status,
		"credential_count": len(credentials),
		"success_count": success_count,
		"processed_events": processed_events,
		"results": results,
	}


def sync_all_channels(
	channels: list[str] | None = None,
	limit: int = 20,
	max_retries: int = 1,
) -> list[dict[str, Any]]:
	target_channels = channels or get_supported_channels()
	return [
		sync_channel(
			channel=channel,
			limit=limit,
			max_retries=max_retries,
		)
		for channel in target_channels
	]


def run_scheduled_pull_sync() -> dict[str, Any]:
	target_channels = _scheduled_channels_from_env()
	limit = max(1, _as_int(os.getenv("CRM_CHANNEL_SYNC_SCHEDULED_LIMIT"), 20))
	max_retries = max(0, _as_int(os.getenv("CRM_CHANNEL_SYNC_SCHEDULED_MAX_RETRIES"), 1))
	results = sync_all_channels(
		channels=target_channels,
		limit=limit,
		max_retries=max_retries,
	)
	failed_channels = [item["channel"] for item in results if item.get("status") == "failed"]
	partial_channels = [item["channel"] for item in results if item.get("status") == "partial"]
	return {
		"channels": [item["channel"] for item in results],
		"items": results,
		"total_count": len(results),
		"failed_channels": failed_channels,
		"partial_channels": partial_channels,
		"limit": limit,
		"max_retries": max_retries,
	}
