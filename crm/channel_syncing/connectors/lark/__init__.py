from __future__ import annotations


def get_connector_meta() -> dict[str, object]:
	return {
		"name": "lark",
		"label": "Lark",
		"direction": ["pull", "webhook"],
		"status": "skeleton",
		"supported_events": ["message.created", "minutes.generated"],
	}
