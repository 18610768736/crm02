from __future__ import annotations

from crm.ai.schemas import ApprovalRequest

CHANNELS_REQUIRING_HUMAN_APPROVAL = {"qywx", "lark", "dingtalk", "wechat_customer", "email"}


def build_approval_request(
	reference_doctype: str, reference_name: str, channel: str | None = None
) -> ApprovalRequest:
	target_channel = channel or "omni"
	reason = "Outbound AI suggestions require human review before sending."
	if target_channel not in CHANNELS_REQUIRING_HUMAN_APPROVAL:
		reason = "Review remains enabled until channel-specific policy is configured."

	return {
		"required": True,
		"policy": "human_review_before_send",
		"reason": reason,
		"channel": target_channel,
		"reference": {"doctype": reference_doctype, "name": reference_name},
	}
