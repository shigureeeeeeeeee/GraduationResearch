import json
import os
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from llm_clients import LLMResult
from ventilation_content import goal_example_program, GROUPS, SCENARIOS, condition, example_program, rule
from ventilation_engine import initial_state, learner_step, reference_step, simulate_reference as simulate
from ventilation_models import AdviceRequest, Program, TestInput
from ventilation_service import context_for, generate_discussion, plan_facts


def inputs(scenario_id):
    scenario = next(item for item in SCENARIOS if item["id"] == scenario_id)
    return [TestInput.model_validate(step) for step in scenario["steps"]]


class LegacyVentilationStateMachineTest(unittest.TestCase):
    def test_documented_eight_step_trace_and_waiting_times(self):
        result = simulate(example_program("complete"), inputs("shared"))
        self.assertEqual([row["after"]["output"] for row in result["trace"]],
                         ["A", "A", "stop", "B", "stop", "A", "stop", "B"])
        self.assertEqual([(row["after"]["wait"]["A"], row["after"]["wait"]["B"])
                          for row in result["trace"]],
                         [(0, 1), (0, 2), (1, 3), (2, 0), (3, 1), (0, 2), (0, 3), (0, 0)])
        self.assertTrue(result["all_correct"])

    def test_same_sensor_reading_depends_on_history(self):
        idle = reference_step(TestInput(aCo2=900, bCo2=700), initial_state())
        active = reference_step(TestInput(aCo2=1100, bCo2=700), initial_state())
        active = reference_step(TestInput(aCo2=900, bCo2=700), active)
        self.assertEqual(idle["output"], "stop")
        self.assertEqual(active["output"], "A")

    def test_thresholds_are_inclusive_and_absence_clears_memory(self):
        state = reference_step(TestInput(aCo2=1000, bCo2=700), initial_state())
        self.assertTrue(state["demand"]["A"])
        stopped = reference_step(TestInput(aCo2=800, bCo2=700), state)
        self.assertFalse(stopped["demand"]["A"])
        absent = reference_step(TestInput(aCo2=1600, bCo2=700, aOccupied=False), state)
        returned = reference_step(TestInput(aCo2=900, bCo2=700), absent)
        self.assertFalse(returned["demand"]["A"])

    def test_urgent_overrides_long_wait_but_not_switching_stop(self):
        state = {"demand": {"A": True, "B": True}, "wait": {"A": 0, "B": 7}, "output": "stop", "run": 0}
        env = TestInput(aCo2=1500, bCo2=1400)
        self.assertEqual(reference_step(env, state)["output"], "A")
        state.update(output="B", run=1)
        self.assertEqual(reference_step(env, state)["output"], "stop")

    def test_cooling_stop_also_allows_switching(self):
        state = {"demand": {"A": True, "B": True}, "wait": {"A": 0, "B": 2}, "output": "A", "run": 2}
        env = TestInput(aCo2=1200, bCo2=1100)
        stopped = reference_step(env, state)
        self.assertEqual(stopped["output"], "stop")
        self.assertEqual(stopped["wait"]["B"], 3)
        self.assertEqual(reference_step(env, stopped)["output"], "B")

    def test_maintenance_resets_counters_but_updates_demand(self):
        state = {"demand": {"A": True, "B": True}, "wait": {"A": 3, "B": 4}, "output": "A", "run": 1}
        stopped = reference_step(TestInput(aCo2=900, bCo2=800, maintenance=True), state)
        self.assertEqual(stopped, {"demand": {"A": True, "B": False}, "wait": {"A": 0, "B": 0}, "output": "stop", "run": 0})

    def test_current_room_continues_before_normal_concentration_ranking(self):
        state = reference_step(TestInput(aCo2=1100, bCo2=1200), initial_state())
        state = reference_step(TestInput(aCo2=1400, bCo2=1100), state)
        self.assertEqual(state["output"], "B")

    def test_ties_break_by_wait_then_room_a(self):
        state = initial_state()
        state["wait"] = {"A": 1, "B": 2}
        self.assertEqual(reference_step(TestInput(aCo2=1500, bCo2=1500), state)["output"], "B")
        self.assertEqual(reference_step(TestInput(aCo2=1500, bCo2=1500), initial_state())["output"], "A")

    def test_known_misconceptions_are_observable_not_silently_corrected(self):
        for group, scenario, step in [("group_a", "memory", 4), ("group_b", "waiting", 4), ("group_c", "shared", 5)]:
            with self.subTest(group=group):
                result = simulate(example_program(group), inputs(scenario))
                self.assertFalse(result["all_correct"])
                first = next(row for row in result["trace"] if not row["ok"])
                self.assertEqual(first["step"], step)
                if group == "group_c":
                    self.assertEqual(first["after"]["output"], "A")
                    self.assertTrue(first["violations"])

    def test_empty_program_and_empty_run_are_not_completed(self):
        self.assertFalse(simulate(Program(), [])['all_correct'])
        self.assertFalse(simulate(Program(), inputs("shared"))['all_correct'])

    def test_all_named_scenarios_and_random_transitions(self):
        program = example_program("complete")
        for scenario in SCENARIOS:
            self.assertTrue(simulate(program, inputs(scenario["id"]))["all_correct"], scenario["id"])
        rng = random.Random(42)
        actual, expected = initial_state(), initial_state()
        for _ in range(1000):
            env = TestInput(aCo2=rng.choice([700, 800, 801, 900, 999, 1000, 1499, 1500, 1800]),
                            bCo2=rng.choice([700, 800, 900, 1000, 1400, 1500, 1800]),
                            aOccupied=rng.random() > .15, bOccupied=rng.random() > .15,
                            maintenance=rng.random() < .08)
            previous = actual["output"]
            actual, _, _ = learner_step(program, env, actual)
            expected = reference_step(env, expected)
            self.assertEqual(actual, expected)
            self.assertLessEqual(actual["run"], 2)
            self.assertFalse(previous in ("A", "B") and actual["output"] in ("A", "B") and previous != actual["output"])

    def test_rule_order_or_negation_and_field_comparisons(self):
        program = Program.model_validate({
            "demand": [rule("d", "on", condition("occupied", True, negate=True), condition("co2", 1000, "gte"), join="any")],
            "selection": [rule("s", "co2")],
            "output": [rule("o", "selected", condition("candidate", "stop", "ne", other_field="previous_output"))],
        })
        state, _, _ = learner_step(program, TestInput(aCo2=700, bCo2=700, aOccupied=False), initial_state())
        self.assertEqual(state["output"], "A")
        data = program.model_dump()
        data["demand"].insert(0, rule("first", "off"))
        state, _, _ = learner_step(Program.model_validate(data), TestInput(), initial_state())
        self.assertEqual(state["output"], "stop")


class VentilationApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for patcher in [patch("ventilation_service.LOG_FILE", root / "logs.jsonl"),
                        patch("ventilation_service.PROMPT_FILE", root / "prompts.json"),
                        patch.dict(os.environ, {"LLM_PROVIDER": "fallback"}, clear=True)]:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def request_body(self):
        return {"program": example_program("group_a").model_dump(),
                "steps": [s.model_dump() for s in inputs("memory")[:4]],
                "predictions": [{"output": "stop", "reason": "濃度で判断した"} for _ in range(4)],
                "reflection": "前回の要求を保持する必要に気づいた。", "phase": 3}

    def test_config_contains_ventilation_only_and_no_complete_solution(self):
        response = self.client.get("/api/ventilation/config")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["scenarios"]), 8)
        self.assertNotIn("コンビニ", response.text)
        self.assertNotIn('"program"', response.text)
        self.assertNotIn("要求待ち時間が長い方を選ぶ", response.text)

    def test_api_rejects_invalid_rules_and_out_of_range_inputs(self):
        program = example_program("complete").model_dump()
        for broken in [dict(program, output=[rule("bad", "door")]),
                       dict(program, demand=[rule("bad", "on", condition("candidate", "A"))]),
                       dict(program, demand=[rule("bad", "on", condition("co2", "anything"))])]:
            self.assertEqual(self.client.post("/api/ventilation/simulate", json={"program": broken, "steps": []}).status_code, 422)
        self.assertEqual(self.client.post("/api/ventilation/simulate", json={"program": program, "steps": [{"aCo2": -1}]}).status_code, 422)

    def test_live_simulation_matches_the_document(self):
        response = self.client.post("/api/ventilation/simulate", json={"program": example_program("complete").model_dump(), "steps": [s.model_dump() for s in inputs("shared")], "task_id": "ventilation-v1"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["all_correct"])

    def test_advice_has_counterexample_and_predictions(self):
        request = self.request_body()
        response = self.client.post("/api/ventilation/advice", json=request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("参考待ち時間", response.json()["facts"])
        self.assertNotIn("参考待ち時間", response.json()["message"])
        self.assertTrue(response.json()["llm"]["fallback"])
        context = json.loads(context_for(AdviceRequest.model_validate(request)))
        self.assertEqual(context["predictions"][0]["reason"], "濃度で判断した")
        self.assertIn("metrics", context)
        self.assertNotIn("first_mismatch", context)

    def test_discussion_round_shows_computed_facts_then_peers_talk(self):
        response = self.client.post("/api/ventilation/group-discussion/stream", json={**self.request_body(), "focus_plan": "group_a"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/x-ndjson", response.headers["content-type"])
        turns = [json.loads(line) for line in response.text.splitlines()]
        # 事実の枠 → 指摘する仲間（次のグループ）→ 案を作ったグループ → 司会役
        self.assertEqual([turn["agent_id"] for turn in turns], ["system", "group_b", "group_a", "facilitator"])
        self.assertIn(plan_facts(goal_example_program("group_a")), turns[0]["text"])
        self.assertTrue(all(turn["llm"]["fallback"] for turn in turns[1:]))

    def test_learner_message_about_own_plan_gets_a_peer_reply(self):
        body = {**self.request_body(), "focus_plan": "learner", "current_message": "待ち時間を先に見たかった"}
        turns = [json.loads(line) for line in self.client.post("/api/ventilation/group-discussion/stream", json=body).text.splitlines()]
        self.assertEqual([turn["agent_id"] for turn in turns], ["group_a", "facilitator"])

    def test_role_clients_are_independent_and_see_previous_turns(self):
        calls = []
        class FakeClient:
            def __init__(self, role): self.role = role
            def chat(self, messages, options):
                calls.append((self.role, messages[-1].content))
                return LLMResult(text="前の状態と今回の判断を比べると、どんな違いがある？", provider="fake", model=self.role, elapsed_ms=2)
        with patch("ventilation_service.create_llm_client", side_effect=lambda role=None: FakeClient(role)):
            turns = list(generate_discussion(AdviceRequest.model_validate({**self.request_body(), "focus_plan": "group_a"})))
        self.assertEqual([role for role, _ in calls], ["group_b", "group_a", "facilitator"])
        self.assertIn(turns[1]["text"], calls[1][1])
        self.assertTrue(all(not turn["llm"]["fallback"] for turn in turns[1:]))

    def test_logs_preserve_predictions_revision_and_server_evaluation_idempotently(self):
        request = {**self.request_body(), "session_id": "test-session", "event_id": "event-1", "event": "program_revision",
                   "next_program": example_program("complete").model_dump(), "task_id": "ventilation-goals-v2"}
        for _ in range(2):
            response = self.client.post("/api/ventilation/log", json=request)
            self.assertEqual(response.status_code, 200, response.text)
        logs = self.client.get("/api/ventilation/log/export").json()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["predictions"][0]["reason"], "濃度で判断した")
        self.assertEqual(logs[0]["next_program"], request["next_program"])
        self.assertNotIn("all_correct", logs[0])
        self.assertIn("metrics", logs[0]["evaluation"])
        self.assertEqual(len(logs[0]["evaluation"]["trace"]), 4)
        # 予想は廃止したので空は受け付けるが、ステップ数と合わない予想は拒否する
        request["event_id"] = "event-2"
        request["predictions"] = request["predictions"][:1]
        self.assertEqual(self.client.post("/api/ventilation/log", json=request).status_code, 422)

    def test_generated_explanation_cannot_replace_computed_facts(self):
        class MisleadingClient:
            text = ""
            def chat(self, messages, options):
                return LLMResult(text=self.text, provider="fake", model="misleading", elapsed_ms=1)
        for text in ("濃度900で要求OFFになり、停止は正当な判断です。", "連続運転数が考慮されていない理由は何だと思いますか？"):
            fake = MisleadingClient()
            fake.text = text
            with patch("ventilation_service.create_llm_client", return_value=fake):
                response = self.client.post("/api/ventilation/advice", json=self.request_body()).json()
            self.assertTrue(response["llm"]["fallback"])
            self.assertIn("制約違反", response["facts"])
            self.assertIn("参考待ち時間", response["facts"])
            self.assertNotIn(text, response["message"])

    def test_repeated_question_punctuation_is_normalized(self):
        class QuestionClient:
            def chat(self, messages, options):
                return LLMResult(text="前の状態と予想を比べると、どんな違いがありますか？？", provider="fake", model="question", elapsed_ms=1)
        with patch("ventilation_service.create_llm_client", return_value=QuestionClient()):
            response = self.client.post("/api/ventilation/advice", json=self.request_body()).json()
        self.assertFalse(response["llm"]["fallback"])
        self.assertTrue(response["message"].endswith("ありますか？"))

    def test_prompt_settings_are_isolated_and_can_be_reset(self):
        old = self.client.get("/api/config/prompts").json()
        prompts = self.client.get("/api/ventilation/config/prompts").json()
        original = dict(prompts)
        prompts["base"] = "換気について問いかける。"
        self.assertEqual(self.client.post("/api/ventilation/config/prompts", json=prompts).status_code, 200)
        self.assertEqual(self.client.get("/api/ventilation/config/prompts").json(), prompts)
        self.assertEqual(self.client.get("/api/config/prompts").json(), old)
        self.client.post("/api/ventilation/config/prompts/reset")
        self.assertEqual(self.client.get("/api/ventilation/config/prompts").json(), original)


if __name__ == "__main__":
    unittest.main()
