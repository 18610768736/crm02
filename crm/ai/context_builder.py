from __future__ import annotations

from crm.ai.schemas import PanelContext

SUPPORTED_CONTEXT_CHANNELS = ("qywx", "lark", "email", "dingtalk")


def build_panel_context(
	reference_doctype: str, reference_name: str, context_type: str = "deal_panel"
) -> PanelContext:
	reference = {"doctype": reference_doctype, "name": reference_name}
	sections = [
		{
			"key": "summary",
			"title": "Summary",
			"items": [
				{"label": "Current stage", "value": "pending_sync"},
				{"label": "Primary channel", "value": "not_synced"},
			],
		},
		{
			"key": "timeline",
			"title": "Timeline",
			"items": [
				{"label": "Last touchpoint", "value": "awaiting_channel_ingest"},
				{"label": "Next milestone", "value": "qualification_review"},
			],
		},
		{
			"key": "next_actions",
			"title": "Next actions",
			"items": [
				{"label": "Suggested owner", "value": "sales_owner"},
				{"label": "Execution mode", "value": "human_review_before_send"},
			],
		},
	]
	actions = [
		{"key": "draft_qywx_followup", "label": "Draft WeCom follow-up"},
		{"key": "draft_email_followup", "label": "Draft email follow-up"},
		{"key": "append_internal_note", "label": "Append internal note"},
	]
	metadata = {
		"source": "crm.ai.context_builder",
		"supported_channels": list(SUPPORTED_CONTEXT_CHANNELS),
		"requires_human_review": True,
	}

	return {
		"reference": reference,
		"context_type": context_type,
		"sections": sections,
		"actions": actions,
		"metadata": metadata,
	}
