from __future__ import annotations

from crm.ai.schemas import AISuggestion


def build_suggestion_cards(
	reference_doctype: str, reference_name: str, channel: str | None = None
) -> list[AISuggestion]:
	target_channel = channel or "email"

	return [
		{
			"key": "next_touch",
			"title": "Draft next touchpoint",
			"channel": target_channel,
			"content": (
				f"Share a concise follow-up for {reference_doctype} {reference_name}, "
				"confirm the decision window, and propose the next meeting."
			),
			"reason": "Keeps momentum while synced interaction history is still sparse.",
		},
		{
			"key": "internal_note",
			"title": "Capture missing internal note",
			"channel": "crm_note",
			"content": "Record budget, stakeholders, timeline, and procurement blockers.",
			"reason": "Improves future grounding quality for AI-generated suggestions.",
		},
	]
