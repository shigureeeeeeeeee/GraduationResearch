import unittest
from unittest.mock import patch

from discussion import generate_discussion
from llm_clients import LLMResult
from schemas import AdviceRequest


RESPONSES = {
    "group_a": "その指摘には同意します。ほかの場面でも同じ観点で比べたいです。",
    "group_b": "Aグループとは注目点が違いますが、一つずつ確かめる考え方には同意します。",
    "group_c": "二つの意見には共通点があります。私たちは別の観点から比べたいです。",
    "facilitator": (
        "Aグループ、Bグループ、Cグループでは注目点が異なります。"
        "自分の案と比べると、どの意見が見直す手がかりになりそうですか？"
    ),
}


class FakeClient:
    def __init__(self, role):
        self.role = role

    def chat(self, messages, options):
        return LLMResult(
            text=RESPONSES[self.role],
            provider="fake",
            model=f"{self.role}-model",
            elapsed_ms=1,
        )


class DiscussionProviderTest(unittest.TestCase):
    def test_each_agent_resolves_its_own_client(self):
        request = AdviceRequest.model_validate(
            {
                "rules": [],
                "environment": {
                    "personPresent": False,
                    "isDark": False,
                },
                "result": {
                    "doorOpen": False,
                    "bellRinging": False,
                    "doorCorrect": True,
                    "bellCorrect": True,
                    "allCorrect": False,
                },
                "history": [],
                "current_message": "それぞれの案を比べたいです。",
                "phase": 4,
            }
        )
        requested_roles = []

        def client_for(role):
            requested_roles.append(role)
            return FakeClient(role)

        with patch("discussion.create_llm_client", side_effect=client_for):
            turns = list(generate_discussion(request))

        self.assertEqual(
            requested_roles,
            ["group_a", "group_b", "group_c", "facilitator"],
        )
        self.assertEqual(len(turns), 4)
        self.assertEqual(
            [turn["llm"]["model"] for turn in turns],
            [
                "group_a-model",
                "group_b-model",
                "group_c-model",
                "facilitator-model",
            ],
        )
        self.assertTrue(all(not turn["llm"]["fallback"] for turn in turns))


if __name__ == "__main__":
    unittest.main()
