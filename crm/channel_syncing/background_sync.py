from __future__ import annotations

from crm.channel_syncing.repository import upsert_sync_cursor

SUPPORTED_CHANNELS = ("qywx", "lark", "email")


def get_supported_channels() -> list[str]:
	return list(SUPPORTED_CHANNELS)


def sync_channel(
	channel: str,
	cursor_key: str | None = None,
	cursor_value: str | None = None,
	max_retries: int = 1,
) -> dict[str, str | int | None]:
	target_cursor_key = cursor_key or f"{channel}::default"
	target_cursor_value = cursor_value or "idle"
	attempt = 0
	last_error: str | None = None

	while attempt < max_retries:
		attempt += 1
		try:
			stored_cursor = upsert_sync_cursor(
				channel=channel,
				cursor_key=target_cursor_key,
				cursor_value=target_cursor_value,
				status="Succeeded",
				retry_count=attempt - 1,
				metadata={"mode": "background_sync_stub"},
			)
			return {
				"channel": channel,
				"status": "idle",
				"cursor_id": stored_cursor["name"],
				"cursor_key": target_cursor_key,
				"cursor_value": target_cursor_value,
				"retry_count": attempt - 1,
				"message": "Connector skeleton ready; pull sync is not wired yet.",
			}
		except Exception as exc:  # pragma: no cover - defensive fallback
			last_error = str(exc)
			upsert_sync_cursor(
				channel=channel,
				cursor_key=target_cursor_key,
				cursor_value=target_cursor_value,
				status="Retrying" if attempt < max_retries else "Failed",
				retry_count=attempt,
				last_error=last_error,
				metadata={"mode": "background_sync_stub"},
			)

	return {
		"channel": channel,
		"status": "failed",
		"cursor_key": target_cursor_key,
		"cursor_value": target_cursor_value,
		"retry_count": max_retries,
		"message": f"Background sync failed after retries: {last_error or 'unknown error'}.",
	}


def sync_all_channels(channels: list[str] | None = None) -> list[dict[str, str | int | None]]:
	target_channels = channels or get_supported_channels()
	return [sync_channel(channel) for channel in target_channels]
