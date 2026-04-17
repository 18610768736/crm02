from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import frappe

from crm.channel_syncing.alerts import list_sync_alerts
from crm.channel_syncing.repository import list_conversation_threads


def _coerce_limit(value: int | str | None, default: int = 10) -> int:
	if value is None:
		return default
	return max(1, int(value))


def _parse_datetime(value: str | None) -> datetime | None:
	if not value:
		return None
	if frappe:
		try:
			return frappe.utils.get_datetime(value)
		except Exception:
			return None
	try:
		return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
	except ValueError:
		return None


def _query_high_risk_suggestions(limit: int) -> list[dict[str, Any]]:
	if not frappe.db.exists("DocType", "AI Suggestion"):
		return []
	rows = frappe.get_all(
		"AI Suggestion",
		filters={"risk_level": "High"},
		fields=[
			"name",
			"title",
			"status",
			"reference_doctype",
			"reference_name",
			"channel",
			"modified",
		],
		order_by="modified desc",
		limit=limit,
	)
	return [
		{
			"name": row.get("name"),
			"title": row.get("title"),
			"status": row.get("status"),
			"channel": row.get("channel"),
			"updated_at": row.get("modified"),
			"reference": {
				"doctype": row.get("reference_doctype"),
				"name": row.get("reference_name"),
			},
		}
		for row in rows
	]


def _query_deals_without_next_step(limit: int) -> list[dict[str, Any]]:
	if not frappe.db.exists("DocType", "CRM Deal"):
		return []
	rows = frappe.get_all(
		"CRM Deal",
		filters={"next_step": ["in", ["", None]]},
		fields=["name", "deal_owner", "status", "modified"],
		order_by="modified desc",
		limit=limit,
	)
	return [
		{
			"name": row.get("name"),
			"deal_owner": row.get("deal_owner"),
			"status": row.get("status"),
			"updated_at": row.get("modified"),
		}
		for row in rows
	]


def _query_stale_threads(stale_days: int, limit: int) -> list[dict[str, Any]]:
	threads = list_conversation_threads(limit=max(limit * 5, 50))
	threshold = datetime.utcnow() - timedelta(days=max(stale_days, 1))
	stale_threads: list[dict[str, Any]] = []
	for thread in threads:
		last_touchpoint = _parse_datetime(thread.get("last_touchpoint_at"))
		if last_touchpoint is None or last_touchpoint <= threshold:
			stale_threads.append(thread)
	stale_threads.sort(key=lambda item: str(item.get("last_touchpoint_at") or ""))
	return stale_threads[:limit]


@frappe.whitelist()
def get_manager_overview(
	limit: int | str | None = 10,
	stale_days: int | str | None = 7,
) -> dict:
	item_limit = _coerce_limit(limit, default=10)
	stale_day_count = max(1, int(stale_days or 7))
	high_risk_suggestions = _query_high_risk_suggestions(item_limit)
	stale_threads = _query_stale_threads(stale_day_count, item_limit)
	sync_alerts = list_sync_alerts(severity="error", limit=item_limit)
	deals_without_next_step = _query_deals_without_next_step(item_limit)

	return {
		"generated_at": frappe.utils.now() if frappe else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
		"stale_days": stale_day_count,
		"high_risk_suggestions": high_risk_suggestions,
		"stale_threads": stale_threads,
		"sync_alerts": sync_alerts,
		"deals_without_next_step": deals_without_next_step,
		"summary": {
			"high_risk_suggestion_count": len(high_risk_suggestions),
			"stale_thread_count": len(stale_threads),
			"sync_alert_count": len(sync_alerts),
			"deals_without_next_step_count": len(deals_without_next_step),
		},
	}

