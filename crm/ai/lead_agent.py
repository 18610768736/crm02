from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

try:
	import frappe
except ModuleNotFoundError:  # pragma: no cover - local non-Frappe environments
	frappe = None

_VOLATILE_AUTO_PROFILES: dict[str, dict[str, Any]] = {}


def _doc_type_available(doctype: str) -> bool:
	return bool(frappe and frappe.db.exists("DocType", doctype))


def _profile_key(profile: dict[str, Any], normalized_event: dict[str, Any]) -> str:
	identities = profile.get("identities") or {}
	for key in ("email", "phone", "external_user_id"):
		value = str(identities.get(key) or "").strip().lower()
		if value:
			return f"{key}::{value}"
	display_name = str(profile.get("display_name") or "").strip().lower()
	if display_name:
		return f"display::{display_name}"
	return f"event::{normalized_event.get('channel')}::{normalized_event.get('external_id')}"


def _split_name(display_name: str | None) -> tuple[str, str | None]:
	text = str(display_name or "").strip()
	if not text:
		return "未知客户", None
	parts = [part for part in text.replace("·", " ").split(" ") if part]
	if len(parts) == 1:
		return parts[0], None
	return parts[0], " ".join(parts[1:])


def extract_profile_from_event(normalized_event: dict[str, Any]) -> dict[str, Any]:
	contact_hints = normalized_event.get("contact_hints", {})
	display_names = contact_hints.get("display_names") or []
	emails = contact_hints.get("emails") or []
	phones = contact_hints.get("phone_numbers") or []
	external_user_ids = contact_hints.get("external_user_ids") or []
	display_name = display_names[0] if display_names else None
	source_payload = normalized_event.get("source_payload") or {}
	organization = (
		source_payload.get("organization")
		or source_payload.get("organization_name")
		or source_payload.get("company_name")
		or source_payload.get("customer_company")
		or source_payload.get("account_name")
	)
	return {
		"display_name": display_name,
		"summary": (normalized_event.get("content") or {}).get("summary"),
		"identities": {
			"email": emails[0] if emails else None,
			"phone": phones[0] if phones else None,
			"external_user_id": external_user_ids[0] if external_user_ids else None,
		},
		"organization": organization,
		"channel": normalized_event.get("channel"),
		"external_id": normalized_event.get("external_id"),
	}


def _default_lead_status() -> str | None:
	if not _doc_type_available("CRM Lead Status"):
		return None
	rows = frappe.get_all("CRM Lead Status", fields=["name"], order_by="modified asc", limit=1)
	if not rows:
		return None
	return rows[0].get("name")


def _find_existing_lead(profile: dict[str, Any]) -> str | None:
	if not _doc_type_available("CRM Lead"):
		return None
	identities = profile.get("identities") or {}
	email = identities.get("email")
	phone = identities.get("phone")
	display_name = profile.get("display_name")
	if email:
		existing = frappe.db.exists("CRM Lead", {"email": email})
		if existing:
			return existing
	if phone:
		existing = frappe.db.exists("CRM Lead", {"mobile_no": phone})
		if existing:
			return existing
	if display_name:
		existing = frappe.db.exists("CRM Lead", {"lead_name": display_name})
		if existing:
			return existing
	return None


def _ensure_organization(profile: dict[str, Any]) -> str | None:
	organization = str(profile.get("organization") or "").strip()
	if not organization or not _doc_type_available("CRM Organization"):
		return None
	existing = frappe.db.exists("CRM Organization", {"organization_name": organization})
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "CRM Organization",
			"organization_name": organization,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_contact(profile: dict[str, Any]) -> str | None:
	if not _doc_type_available("Contact"):
		return None
	identities = profile.get("identities") or {}
	email = identities.get("email")
	phone = identities.get("phone")
	if email:
		existing = frappe.db.exists("Contact", {"email_id": email})
		if existing:
			return existing

	first_name, last_name = _split_name(profile.get("display_name"))
	payload: dict[str, Any] = {"doctype": "Contact", "first_name": first_name}
	if last_name:
		payload["last_name"] = last_name
	if email:
		payload["email_id"] = email
	if phone:
		payload["mobile_no"] = phone
	doc = frappe.get_doc(payload)
	doc.insert(ignore_permissions=True)
	return doc.name


def _create_lead(profile: dict[str, Any]) -> str:
	existing = _find_existing_lead(profile)
	if existing:
		return existing

	first_name, _ = _split_name(profile.get("display_name"))
	identities = profile.get("identities") or {}
	payload: dict[str, Any] = {
		"doctype": "CRM Lead",
		"first_name": first_name,
		"lead_name": profile.get("display_name") or first_name,
		"email": identities.get("email"),
		"mobile_no": identities.get("phone"),
		"organization": profile.get("organization"),
	}
	lead_status = _default_lead_status()
	if lead_status:
		payload["status"] = lead_status
	doc = frappe.get_doc(payload)
	doc.insert(ignore_permissions=True)
	return doc.name


def _create_profile_in_frappe(profile: dict[str, Any]) -> dict[str, Any]:
	lead_id = _create_lead(profile)
	organization_id = None
	contact_id = None
	try:
		organization_id = _ensure_organization(profile)
	except Exception:
		organization_id = None
	try:
		contact_id = _ensure_contact(profile)
	except Exception:
		contact_id = None
	return {
		"lead_id": lead_id,
		"organization_id": organization_id,
		"contact_id": contact_id,
	}


def _create_profile_volatile(profile: dict[str, Any], key: str) -> dict[str, Any]:
	existing = _VOLATILE_AUTO_PROFILES.get(key)
	if existing:
		return deepcopy(existing)
	record = {
		"lead_id": f"LEAD-AUTO-{uuid.uuid4().hex[:8].upper()}",
		"organization_id": (
			f"ORG-AUTO-{uuid.uuid4().hex[:8].upper()}" if profile.get("organization") else None
		),
		"contact_id": (
			f"CONTACT-AUTO-{uuid.uuid4().hex[:8].upper()}"
			if (profile.get("identities") or {}).get("email")
			or (profile.get("identities") or {}).get("phone")
			else None
		),
	}
	_VOLATILE_AUTO_PROFILES[key] = deepcopy(record)
	return deepcopy(record)


def ensure_reference_for_event(
	normalized_event: dict[str, Any],
	match_result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
	if (match_result.get("reference") or {}).get("doctype"):
		return match_result, None

	profile = extract_profile_from_event(normalized_event)
	key = _profile_key(profile, normalized_event)

	try:
		if _doc_type_available("CRM Lead"):
			created = _create_profile_in_frappe(profile)
		else:
			created = _create_profile_volatile(profile, key)
	except Exception:
		created = _create_profile_volatile(profile, key)

	reference = {"doctype": "CRM Lead", "name": created["lead_id"]}
	confidence = max(float(match_result.get("confidence") or 0), 0.55)
	thread_match = dict(match_result.get("thread_match") or {})
	thread_match.setdefault("thread_key", normalized_event.get("thread_key"))
	thread_match["thread_strategy"] = "auto_profile_creation"
	thread_match["thread_confidence"] = max(float(thread_match.get("thread_confidence") or 0), confidence)
	updated_match = {
		**match_result,
		"matched": True,
		"confidence": confidence,
		"reference": reference,
		"strategy": "auto_profile_creation",
		"thread_match": thread_match,
	}
	return updated_match, {
		"profile_key": key,
		"profile": profile,
		"created": created,
		"reference": reference,
	}
