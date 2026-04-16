from __future__ import annotations

from typing import Any

from crm.channel_syncing.connectors.email import get_connector_meta as get_email_connector_meta
from crm.channel_syncing.connectors.lark import get_connector_meta as get_lark_connector_meta
from crm.channel_syncing.connectors.qywx import get_connector_meta as get_qywx_connector_meta

CONNECTORS = {
	"qywx": get_qywx_connector_meta,
	"lark": get_lark_connector_meta,
	"email": get_email_connector_meta,
}


def get_supported_connectors() -> list[str]:
	return list(CONNECTORS)


def get_connector_meta(channel: str) -> dict[str, Any]:
	factory = CONNECTORS.get(channel)
	if not factory:
		return {"name": channel, "status": "unsupported"}
	return factory()
