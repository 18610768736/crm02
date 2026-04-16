from __future__ import annotations

from typing import Any


def build_sync_evidence(normalized_event: dict[str, Any]) -> dict[str, Any]:
	return {
		"evidence_key": (
			f"channel::{normalized_event['channel']}::{normalized_event['external_id']}"
		),
		"channel": normalized_event["channel"],
		"summary": normalized_event["content"]["summary"],
		"captured_fields": list(normalized_event.get("contact_hints", {}).keys()),
		"raw_event": normalized_event,
	}


def build_sync_evidence_links(normalized_event: dict[str, Any]) -> list[dict[str, Any]]:
	channel = normalized_event["channel"]
	external_id = normalized_event["external_id"]
	summary = normalized_event["content"]["summary"]
	return [
		{
			"evidence_key": f"channel::{channel}::{external_id}",
			"title": f"{channel} event {external_id}",
			"channel": channel,
			"source_type": "channel_event",
			"source_ref": f"{channel}::{external_id}",
			"summary": summary,
			"raw_payload": normalized_event,
		}
	]
