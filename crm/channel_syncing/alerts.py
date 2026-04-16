from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any

try:
	import frappe
except ModuleNotFoundError:  # pragma: no cover - local non-Frappe environments
	frappe = None

_VOLATILE_ALERTS: dict[str, dict[str, Any]] = {}


def _now_text() -> str:
	if frappe:
		return frappe.utils.now()
	return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def emit_sync_alert(
	channel: str,
	code: str,
	message: str,
	severity: str = "warning",
	context: dict[str, Any] | None = None,
) -> dict[str, Any]:
	alert_id = f"SYNC-ALERT-{uuid.uuid4().hex[:10]}"
	payload = {
		"name": alert_id,
		"channel": channel,
		"code": code,
		"severity": severity,
		"message": message,
		"context": context or {},
		"created_at": _now_text(),
	}
	_VOLATILE_ALERTS[alert_id] = deepcopy(payload)

	if frappe:
		title = f"[{severity.upper()}] {channel}::{code}"
		frappe.log_error(title=title, message=message)

	return deepcopy(payload)


def list_sync_alerts(
	channel: str | None = None,
	severity: str | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	items = []
	for record in _VOLATILE_ALERTS.values():
		if channel and record.get("channel") != channel:
			continue
		if severity and record.get("severity") != severity:
			continue
		items.append(deepcopy(record))
	items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
	return items[:limit]


def reset_sync_alerts() -> None:
	_VOLATILE_ALERTS.clear()
