from __future__ import annotations

from typing import Any


def match_event_to_reference(normalized_event: dict[str, Any]) -> dict[str, Any]:
	source_payload = normalized_event.get("source_payload", {})
	reference_doctype = source_payload.get("reference_doctype")
	reference_name = source_payload.get("reference_name")
	if reference_doctype and reference_name:
		return {
			"matched": True,
			"confidence": 1.0,
			"reference": {"doctype": reference_doctype, "name": reference_name},
			"strategy": "explicit_reference_hint",
			"thread_match": {
				"thread_key": normalized_event.get("thread_key"),
				"thread_confidence": 1.0,
				"thread_strategy": "explicit_reference_hint",
			},
		}

	contact_hints = normalized_event.get("contact_hints", {})
	signal_count = sum(1 for values in contact_hints.values() if values)

	if signal_count >= 3:
		confidence = 0.8
	elif signal_count >= 1:
		confidence = 0.4
	else:
		confidence = 0.0

	return {
		"matched": False,
		"confidence": confidence,
		"reference": None,
		"strategy": "skeleton_identity_matching",
		"thread_match": {
			"thread_key": normalized_event.get("thread_key"),
			"thread_confidence": max(confidence, 0.5),
			"thread_strategy": "channel_thread_key",
		},
	}
