from __future__ import annotations


def get_connector_meta() -> dict[str, object]:
	return {
		"name": "qywx",
		"label": "WeCom",
		"direction": ["pull", "webhook"],
		"status": "skeleton",
		"supported_events": ["message.created", "customer.updated"],
	}
