from __future__ import annotations


def get_connector_meta() -> dict[str, object]:
	return {
		"name": "email",
		"label": "Email",
		"direction": ["pull"],
		"status": "skeleton",
		"supported_events": ["message.created", "message.replied"],
	}
