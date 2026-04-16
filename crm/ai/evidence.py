from __future__ import annotations

from typing import Any

from crm.ai.schemas import PanelContext


def build_evidence_packet(
	context: PanelContext, normalized_events: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
	return {
		"reference": context["reference"],
		"summary": "Skeleton evidence packet grounded in CRM panel context.",
		"source_types": ["crm_panel", "channel_sync"],
		"events": normalized_events or [],
	}


def build_evidence_links(evidence_packet: dict[str, Any], channel: str | None = None) -> list[dict[str, Any]]:
	reference = evidence_packet.get("reference") or {}
	reference_doctype = reference.get("doctype") or "Unknown"
	reference_name = reference.get("name") or "UNKNOWN"
	base_key = f"evidence::{reference_doctype}::{reference_name}"
	events = evidence_packet.get("events") or []
	links: list[dict[str, Any]] = []

	for index, event in enumerate(events):
		event_channel = event.get("channel") or channel or "unknown"
		event_external_id = event.get("external_id") or f"event-{index}"
		summary = (event.get("content") or {}).get("summary") or evidence_packet.get("summary")
		links.append(
			{
				"evidence_key": f"{base_key}::{event_channel}::{event_external_id}",
				"title": f"{event_channel} event {event_external_id}",
				"channel": event_channel,
				"source_type": "channel_event",
				"source_ref": f"{event_channel}::{event_external_id}",
				"summary": summary,
				"raw_payload": event,
			}
		)

	if links:
		return links

	return [
		{
			"evidence_key": f"{base_key}::panel_context",
			"title": "CRM panel context snapshot",
			"channel": channel,
			"source_type": "crm_panel",
			"source_ref": f"{reference_doctype}::{reference_name}",
			"summary": evidence_packet.get("summary"),
			"raw_payload": {
				"source_types": evidence_packet.get("source_types", []),
				"events_count": 0,
			},
		}
	]
