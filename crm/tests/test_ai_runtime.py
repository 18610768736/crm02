from frappe.tests import UnitTestCase

from crm.ai.agent_client import execute_agent_request


class TestAIRuntime(UnitTestCase):
	def test_execute_agent_request_returns_runtime_response(self):
		result = execute_agent_request(
			{
				"provider": "clawx",
				"mode": "crm_copilot",
				"prompt": "正常请求",
			}
		)

		self.assertEqual(result["status"], "succeeded")
		self.assertGreaterEqual(result["attempts"], 1)
		self.assertIn("run_id", result["response"])

	def test_execute_agent_request_retries_and_fails_on_retryable_error(self):
		result = execute_agent_request(
			{
				"provider": "clawx",
				"mode": "crm_copilot",
				"prompt": "[force_retryable_error]",
			},
			max_retries=1,
		)

		self.assertEqual(result["status"], "failed")
		self.assertEqual(result["attempts"], 2)
		self.assertTrue(result["error"]["retryable"])

	def test_execute_agent_request_fails_fast_on_non_retryable_error(self):
		result = execute_agent_request(
			{
				"provider": "clawx",
				"mode": "crm_copilot",
				"prompt": "[force_fatal_error]",
			},
			max_retries=2,
		)

		self.assertEqual(result["status"], "failed")
		self.assertEqual(result["attempts"], 1)
		self.assertFalse(result["error"]["retryable"])
