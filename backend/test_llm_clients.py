import os
import unittest
from unittest.mock import patch

from llm_clients import (
    FallbackClient,
    GeminiClient,
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


if __name__ == "__main__":
    unittest.main()
