from __future__ import annotations

from typing import Any

from crm.channel_syncing.connectors.email import get_connector_meta as get_email_connector_meta
from crm.channel_syncing.connectors.email import (
	normalize_inbound_payload as normalize_email_inbound_payload,
)
from crm.channel_syncing.connectors.email import pull_events as pull_email_events
from crm.channel_syncing.connectors.lark import get_connector_meta as get_lark_connector_meta
from crm.channel_syncing.connectors.lark import normalize_inbound_payload as normalize_lark_inbound_payload
from crm.channel_syncing.connectors.lark import pull_events as pull_lark_events
from crm.channel_syncing.connectors.qywx import get_connector_meta as get_qywx_connector_meta
from crm.channel_syncing.connectors.qywx import normalize_inbound_payload as normalize_qywx_inbound_payload
from crm.channel_syncing.connectors.qywx import pull_events as pull_qywx_events

CONNECTORS = {
	"qywx": get_qywx_connector_meta,
	"lark": get_lark_connector_meta,
	"email": get_email_connector_meta,
}
NORMALIZERS = {
	"qywx": normalize_qywx_inbound_payload,
	"lark": normalize_lark_inbound_payload,
	"email": normalize_email_inbound_payload,
}
PULLERS = {
	"qywx": pull_qywx_events,
	"lark": pull_lark_events,
	"email": pull_email_events,
}


def get_supported_connectors() -> list[str]:
	return list(CONNECTORS)


def get_connector_meta(channel: str) -> dict[str, Any]:
	factory = CONNECTORS.get(channel)
	if not factory:
		return {"name": channel, "status": "unsupported"}
	return factory()


def normalize_connector_payload(channel: str, payload: dict[str, Any]) -> dict[str, Any]:
	normalizer = NORMALIZERS.get(channel)
	if not normalizer:
		return payload
	return normalizer(payload)


def pull_connector_events(
	channel: str,
	credential: dict[str, Any],
	cursor: dict[str, Any] | None = None,
	limit: int = 20,
) -> dict[str, Any]:
	puller = PULLERS.get(channel)
	if not puller:
		raise ValueError(f"Unsupported connector for pull sync: {channel}")
	return puller(credential, cursor=cursor, limit=limit)
