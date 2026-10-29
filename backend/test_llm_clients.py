import os
import unittest
from unittest.mock import patch

from llm_clients import (
    FallbackClient,
    GeminiClient,
    GenerationOptions,
    LLMMessage,
    OllamaClient,
    create_llm_client,
    resolve_llm_config,
)


class LLMConfigTest(unittest.TestCase):
    def test_role_inherits_shared_provider_and_model(self):
        environment = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_MODEL": "shared-model",
        }
        with patch.dict(os.environ, environment, clear=True):
            config = resolve_llm_config("group_a")

        self.assertEqual(config.provider, "ollama")
        self.assertEqual(config.model, "shared-model")

    def test_role_can_override_provider_and_model(self):
        environment = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_MODEL": "shared-model",
            "GEMINI_API_KEY": "test-key",
            "GROUP_B_LLM_PROVIDER": "gemini",
            "GROUP_B_LLM_MODEL": "group-b-model",
        }
        with patch.dict(os.environ, environment, clear=True):
            config = resolve_llm_config("group_b")
            client = create_llm_client("group_b")

        self.assertEqual(config.provider, "gemini")
        self.assertEqual(config.model, "group-b-model")
        self.assertIsInstance(client, GeminiClient)

    def test_each_role_can_use_a_different_ollama_model(self):
        environment = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_MODEL": "shared-model",
            "GROUP_A_LLM_MODEL": "model-a",
            "GROUP_C_LLM_MODEL": "model-c",
        }
        with patch.dict(os.environ, environment, clear=True):
            group_a = create_llm_client("group_a")
            group_b = create_llm_client("group_b")
            group_c = create_llm_client("group_c")

        self.assertIsInstance(group_a, OllamaClient)
        self.assertEqual(group_a.model, "model-a")
        self.assertEqual(group_b.model, "shared-model")
        self.assertEqual(group_c.model, "model-c")

    def test_auto_falls_back_without_credentials_or_model(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "auto"}, clear=True):
            config = resolve_llm_config("facilitator")
            client = create_llm_client("facilitator")

        self.assertEqual(config.provider, "fallback")
        self.assertIsInstance(client, FallbackClient)

    def test_explicit_provider_does_not_depend_on_shared_provider(self):
        environment = {
            "LLM_PROVIDER": "ollama",
            "GEMINI_API_KEY": "test-key",
            "GEMINI_MODEL": "gemini-test",
        }
        with patch.dict(os.environ, environment, clear=True):
            client = create_llm_client(provider="gemini")

        self.assertIsInstance(client, GeminiClient)
        self.assertEqual(client.model, "gemini-test")



class AnthropicClientTest(unittest.TestCase):
    def test_messages_are_shaped_into_alternating_turns_starting_with_user(self):
        from anthropic_client import to_anthropic_messages
        system, turns = to_anthropic_messages([
            LLMMessage("system", "仲間として話す"), LLMMessage("system", "出力の形"),
            LLMMessage("assistant", "ぼくも作ってみたよ"), LLMMessage("user", "待ち時間を先にした"), LLMMessage("user", "どう思う？"),
        ])
        self.assertEqual(system, "仲間として話す\n\n出力の形")
        self.assertEqual([turn["role"] for turn in turns], ["user", "assistant", "user"])
        self.assertIn("どう思う？", turns[-1]["content"])

    def test_request_sends_no_sampling_parameters_and_reads_text(self):
        from types import SimpleNamespace
        from anthropic_client import AnthropicClient
        calls = []
        class FakeMessages:
            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(stop_reason="end_turn", usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                                       content=[SimpleNamespace(type="text", text="ぼくは濃度を先にしたよ。そっちは？")])
        client = AnthropicClient("claude-haiku-5-5", client=SimpleNamespace(messages=FakeMessages()))
        result = client.chat([LLMMessage("system", "s"), LLMMessage("user", "u")], GenerationOptions(temperature=0.45, max_tokens=180))
        self.assertEqual(result.provider, "anthropic")
        self.assertNotIn("temperature", calls[0])
        self.assertEqual(calls[0]["model"], "claude-haiku-5-5")

    def test_refusal_becomes_an_error_so_the_fallback_is_used(self):
        from types import SimpleNamespace
        from anthropic_client import AnthropicClient
        class Refusing:
            def create(self, **kwargs):
                return SimpleNamespace(stop_reason="refusal", content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=0))
        client = AnthropicClient("claude-haiku-5-5", client=SimpleNamespace(messages=Refusing()))
        with self.assertRaises(RuntimeError):
            client.chat([LLMMessage("user", "u")], GenerationOptions())

    def test_role_override_selects_claude_for_one_agent(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "OLLAMA_MODEL": "qwen2.5:7b-instruct",
                                     "FACILITATOR_LLM_PROVIDER": "anthropic"}, clear=True):
            self.assertEqual(resolve_llm_config("facilitator").model, "claude-haiku-5-5")
            self.assertEqual(resolve_llm_config("group_a").provider, "ollama")


if __name__ == "__main__":
    unittest.main()
