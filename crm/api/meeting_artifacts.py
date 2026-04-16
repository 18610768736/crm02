import frappe

from crm.channel_syncing.repository import (
	get_meeting_artifact,
	list_meeting_artifacts as list_stored_meeting_artifacts,
)


def _coerce_limit(value: int | str | None, default: int = 20) -> int:
	if value is None:
		return default
	return max(1, int(value))


@frappe.whitelist()
def list_meeting_artifacts(
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	channel: str | None = None,
	limit: int | str | None = 20,
) -> dict:
	items = list_stored_meeting_artifacts(
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		channel=channel,
		limit=_coerce_limit(limit),
	)
	return {
		"filters": {
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"channel": channel,
		},
		"items": items,
		"total_count": len(items),
	}


@frappe.whitelist()
def get_meeting_artifact_detail(artifact_id: str) -> dict:
	return get_meeting_artifact(artifact_id)
