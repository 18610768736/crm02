from __future__ import annotations

from typing import Any, TypedDict


class CRMReference(TypedDict):
	doctype: str
	name: str


class ContextSection(TypedDict):
	key: str
	title: str
	items: list[dict[str, Any]]


class PanelContext(TypedDict):
	reference: CRMReference
	context_type: str
	sections: list[ContextSection]
	actions: list[dict[str, Any]]
	metadata: dict[str, Any]


class AISuggestion(TypedDict):
	key: str
	title: str
	channel: str
	content: str
	reason: str


class AIJob(TypedDict):
	job_id: str
	job_type: str
	status: str


class ApprovalRequest(TypedDict):
	required: bool
	policy: str
	reason: str
	channel: str
	reference: CRMReference


class SuggestionResponse(TypedDict):
	status: str
	reference: CRMReference
	job: AIJob
	agent_request: dict[str, Any]
	approval: ApprovalRequest
	evidence: dict[str, Any]
	suggestions: list[AISuggestion]
	suggestion_ids: list[str]
	audit_id: str
	evidence_ids: list[str]
	audit: dict[str, Any]
