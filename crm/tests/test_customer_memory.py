from frappe.tests import UnitTestCase

from crm.api.ai import compile_customer_memory, get_customer_memory, list_customer_memories
from crm.api.ai import generate_suggestions
from crm.api.channel_sync import ingest_event


class TestCustomerMemory(UnitTestCase):
	def test_compile_customer_memory_persists_summary_and_signals(self):
		ingest_event(
			"email",
			{
				"event_id": "evt-memory-001",
				"thread_id": "thread-memory-001",
				"subject": "客户记忆测试",
				"body": "请安排产品演示和报价沟通。",
				"from_email": "memory001@example.com",
				"customer_name": "记忆客户A",
				"reference_doctype": "CRM Lead",
				"reference_name": "LEAD-MEMORY-001",
			},
		)
		generate_suggestions(
			"CRM Lead",
			"LEAD-MEMORY-001",
			channel="email",
			prompt="请总结客户近期互动并给出下一步建议",
		)

		memory = compile_customer_memory("CRM Lead", "LEAD-MEMORY-001")
		self.assertEqual(memory["reference"]["doctype"], "CRM Lead")
		self.assertEqual(memory["reference"]["name"], "LEAD-MEMORY-001")
		self.assertTrue(memory["summary"])
		self.assertGreater(memory["source_count"], 0)
		self.assertGreaterEqual(memory["signals"]["touchpoint_count"], 1)

		detail = get_customer_memory("CRM Lead", "LEAD-MEMORY-001")
		self.assertEqual(detail["memory_key"], memory["memory_key"])
		self.assertEqual(detail["reference"]["name"], "LEAD-MEMORY-001")

	def test_list_customer_memories_supports_reference_filter(self):
		compile_customer_memory("CRM Lead", "LEAD-MEMORY-001")
		compile_customer_memory("CRM Deal", "DEAL-MEMORY-001")

		lead_memories = list_customer_memories(reference_doctype="CRM Lead")
		self.assertGreaterEqual(lead_memories["total_count"], 1)
		self.assertTrue(
			all(item["reference"]["doctype"] == "CRM Lead" for item in lead_memories["items"])
		)

