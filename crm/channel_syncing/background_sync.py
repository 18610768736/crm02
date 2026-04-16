from __future__ import annotations

SUPPORTED_CHANNELS = ("qywx", "lark", "email")


def get_supported_channels() -> list[str]:
	return list(SUPPORTED_CHANNELS)


def sync_channel(channel: str) -> dict[str, str]:
	return {
		"channel": channel,
		"status": "idle",
		"message": "Connector skeleton ready; pull sync is not wired yet.",
	}


def sync_all_channels(channels: list[str] | None = None) -> list[dict[str, str]]:
	target_channels = channels or get_supported_channels()
	return [sync_channel(channel) for channel in target_channels]
