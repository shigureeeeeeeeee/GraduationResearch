import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from main import app
from ventilation_content import SCENARIOS, example_program, goal_example_program, rule, condition
from ventilation_engine import simulate
from ventilation_models import AdviceRequest, Program, SessionLog, SimulationBaseline, TestInput
from ventilation_service import append_log, context_for, first_problem, generate_discussion, normalize_question, plan_facts, valid_question
from llm_clients import LLMResult
from ventilation_describe import program_differences
import os


class GoalEvaluationTest(unittest.TestCase):
    def test_different_safe_policies_are_not_graded_against_one_answer(self):
        steps = [TestInput(aCo2=1400, bCo2=1100) for _ in range(8)]
        concentration = simulate(goal_example_program("group_a"), steps)
        waiting = simulate(goal_example_program("group_b"), steps)
        self.assertTrue(concentration["constraints_met"])
        self.assertTrue(waiting["constraints_met"])
        self.assertNotEqual([r["after"]["output"] for r in concentration["trace"]],
                            [r["after"]["output"] for r in waiting["trace"]])
        self.assertGreater(concentration["metrics"]["max_wait"]["B"], waiting["metrics"]["max_wait"]["B"])
        self.assertNotIn("all_correct", concentration)
        self.assertNotIn("expected", concentration["trace"][0])

    def test_turning_requests_off_does_not_erase_observed_wait(self):
        result = simulate(Program(), [TestInput(aCo2=1600, bCo2=700) for _ in range(4)])
        self.assertTrue(result["constraints_met"])
        self.assertEqual(result["state"]["wait"]["A"], 0)
        self.assertEqual(result["metrics"]["max_wait"]["A"], 4)
        self.assertEqual(result["metrics"]["urgent_unserved_room_steps"], 4)
        self.assertEqual(result["metrics"]["served_room_steps"], 0)

    def test_invalid_commands_cannot_receive_goal_credit(self):
        program = Program.model_validate({"demand": [rule("d", "on")],
            "selection": [rule("s", "co2")], "output": [rule("o", "selected")]})
        result = simulate(program, [TestInput(aCo2=1200, bCo2=700) for _ in range(4)])
        self.assertEqual(result["metrics"]["violation_steps"], 2)
        self.assertEqual(result["metrics"]["served_room_steps"], 2)
        self.assertEqual(result["metrics"]["max_wait"]["A"], 2)
        self.assertFalse(result["constraints_met"])
        self.assertEqual(result["state"]["run"], 4)  # No silent hardware correction.

    def test_maintenance_is_excluded_and_clears_reference_wait(self):
        result = simulate(Program(), [TestInput(aCo2=1000, bCo2=700),
            TestInput(aCo2=1500, bCo2=1500, maintenance=True), TestInput(aCo2=1000, bCo2=700)])
        self.assertEqual(result["metrics"]["needs_room_steps"], 2)
        self.assertEqual(result["metrics"]["max_wait"]["A"], 1)
        self.assertEqual(result["trace"][1]["observation"]["goal_wait"], {"A": 0, "B": 0})

    def test_guidance_boundaries_are_observations_not_required_request_rules(self):
        result = simulate(Program(), [TestInput(aCo2=999, bCo2=700), TestInput(aCo2=1000, bCo2=700),
            TestInput(aCo2=1499, bCo2=700), TestInput(aCo2=1500, bCo2=700),
            TestInput(aCo2=1800, bCo2=700, aOccupied=False)])
        self.assertEqual(result["metrics"]["needs_room_steps"], 3)
        self.assertEqual(result["metrics"]["urgent_unserved_room_steps"], 1)
        self.assertTrue(result["constraints_met"])

    def test_unoccupied_and_low_concentration_operation_are_separate_observations(self):
        program = Program.model_validate({"demand": [rule("d", "on")],
            "selection": [rule("s", "room_a")], "output": [rule("o", "selected")]})
        result = simulate(program, [TestInput(aCo2=700, aOccupied=False), TestInput(aCo2=900)])
        self.assertEqual(result["metrics"]["unoccupied_ventilation_steps"], 1)
        self.assertEqual(result["metrics"]["below_guidance_ventilation_steps"], 1)
        self.assertEqual(result["metrics"]["needs_room_steps"], 2)  # B stays at 1,100.

    def test_no_execution_is_not_constraint_verification(self):
        self.assertFalse(simulate(Program(), [])["constraints_met"])

    def test_all_discussion_policies_respect_hardware_on_every_scenario(self):
        for group in ("group_a", "group_b", "group_c"):
            for scenario in SCENARIOS:
                steps = [TestInput.model_validate(s) for s in scenario["steps"]]
                self.assertTrue(simulate(goal_example_program(group), steps)["constraints_met"], (group, scenario["id"]))


class GoalApiAndLoggingTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_new_config_separates_goals_constraints_and_guidance(self):
        config = self.client.get("/api/ventilation/config").json()
        self.assertEqual(config["task_id"], "ventilation-goals-v3")
        self.assertEqual(len(config["goals"]), 3)
        self.assertEqual(len(config["constraints"]), 4)
        self.assertNotIn("待ち時間 → 濃度 → A室", json.dumps(config["constraints"], ensure_ascii=False))

    def test_api_default_observes_goals_and_explicit_v1_retains_legacy_evaluation(self):
        body = {"program": goal_example_program("group_b").model_dump(), "steps": [TestInput().model_dump()]}
        current = self.client.post("/api/ventilation/simulate", json=body).json()
        self.assertIn("metrics", current)
        self.assertNotIn("all_correct", current)
        legacy = self.client.post("/api/ventilation/simulate", json={**body, "task_id": "ventilation-v1"}).json()
        self.assertIn("all_correct", legacy)

    def test_ai_context_has_observations_without_a_policy_oracle(self):
        context = json.loads(context_for(AdviceRequest(program=Program(), steps=[TestInput()])))
        self.assertIn("metrics", context)
        self.assertIn("observation", context["focus_event"])
        self.assertNotIn("expected", context["focus_event"])
        self.assertNotIn("first_mismatch", context)

    def test_new_and_legacy_events_keep_their_original_evaluation_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("ventilation_service.LOG_FILE", Path(directory) / "logs.jsonl"):
                for task_id in ("ventilation-v1", "ventilation-goals-v2", "ventilation-goals-v3"):
                    entry = SessionLog(task_id=task_id, program=Program(), steps=[TestInput()],
                        predictions=[{"output": "stop"}], session_id=task_id, event_id=task_id, event="step")
                    record = append_log(entry)
                    self.assertEqual(record["task_id"], task_id)
                    self.assertEqual("all_correct" in record, task_id == "ventilation-v1")
                    self.assertEqual("goals_met" in record, task_id == "ventilation-goals-v3")
        self.assertEqual(SessionLog(program=Program(), session_id="old", event_id="old", event="reset").task_id, "ventilation-v1")

    def test_step_logs_accept_no_predictions_but_reject_partial_ones(self):
        common = dict(task_id="ventilation-goals-v3", program=Program(), steps=[TestInput(), TestInput()],
                      session_id="s", event_id="e", event="step")
        self.assertEqual(SessionLog(**common).predictions, [])
        self.assertEqual(len(SessionLog(**common, predictions=[{"output": "stop"}] * 2).predictions), 2)
        with self.assertRaises(ValueError):
            SessionLog(**common, predictions=[{"output": "stop"}])


class GeneratedQuestionTest(unittest.TestCase):
    def test_rule_terms_are_allowed_but_state_claims_are_not(self):
        self.assertTrue(valid_question("要求ONの部屋が両方あるとき、どちらを選ぶ理由を説明できますか？"))
        self.assertTrue(valid_question("要求OFFに戻す条件は、どの情報を見て決めましたか？"))
        self.assertTrue(valid_question("要求ON/OFFの条件は、どの情報を見て決めましたか？"))
        self.assertFalse(valid_question("A室の換気要求はONなので、待ち時間をどう考えますか？"))
        self.assertFalse(valid_question("待ち時間を見たよ。濃度も見たよ。継続も見たよ。点検も見たよ。どっちが大事？"))
        self.assertFalse(valid_question("ぼくは高濃度への対応を重視するようにしたんだ。？"))
        self.assertFalse(valid_question("全体では6分しかsembuしていないけど、問題ある？", allowed_numbers={"6"}))
        self.assertTrue(valid_question("1,000ppmを超えたら要求ONにしたけど、どう思う？"))
        self.assertTrue(valid_question("800以下で要求をOFFにする理由って何？"))
        self.assertFalse(valid_question("A室はOFFになってるけど、なんで？"))

    def test_rule_terms_survive_cleanup_and_lines_are_joined_with_a_period(self):
        self.assertEqual(normalize_question("要求ON/OFFの条件はどう決めた？"), "要求ON/OFFの条件はどう決めた？")
        self.assertTrue(valid_question(normalize_question("要求ON/OFFの条件はどう決めた？")))
        self.assertEqual(normalize_question("濃度を先にした\nどうして待ち時間を先にしたの？"), "濃度を先にした。どうして待ち時間を先にしたの？")

    def test_facilitator_alternates_between_the_two_question_types(self):
        captured = []
        class Fake:
            def chat(self, messages, options):
                captured.append(messages[0].content)
                return LLMResult(text="この自習室ならどっちが合ってると思う？", provider="fake", model="f", elapsed_ms=1)
        history = [{"role": "ai", "speaker": "司会役", "phase": 4, "text": "あいさつ"}]
        kinds = []
        with patch("ventilation_service.create_llm_client", return_value=Fake()):
            for _ in range(3):
                captured.clear()
                req = AdviceRequest.model_validate({"program": Program().model_dump(), "phase": 4, "focus_plan": "group_a", "history": history})
                turns = list(generate_discussion(req))
                kinds.append("compare" if "共通点" in captured[-1] else "purpose")
                history += [{"role": turn["role"], "speaker": turn["speaker"], "phase": 4, "text": turn["text"]} for turn in turns]
        self.assertEqual(kinds, ["compare", "purpose", "compare"])

    def test_learner_is_called_you_in_visible_fallbacks(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "fallback"}):
            req = AdviceRequest.model_validate({"program": Program().model_dump(), "phase": 4, "focus_plan": "learner"})
            texts = [turn["text"] for turn in generate_discussion(req)]
        self.assertTrue(any("あなたの案" in text for text in texts))
        self.assertFalse(any("学習者" in text for text in texts))

    def test_copied_labels_and_extra_questions_are_cleaned(self):
        raw = "自分の考えや迷い: 濃度を先に見たけど迷ってる。\n相手への問い: 待ち時間はどう考えた？？それとも濃度だけ？"
        self.assertEqual(normalize_question(raw), "濃度を先に見たけど迷ってる。待ち時間はどう考えた？")
        self.assertTrue(valid_question(normalize_question(raw)))
        self.assertEqual(normalize_question("司会役: この自習室ならどっちが合ってると思う？"), "この自習室ならどっちが合ってると思う？")
        self.assertFalse(valid_question("その結果、B室が放置されたのは理解できますか？"))

    def test_peer_utterances_reject_teacher_talk_and_unsupported_numbers(self):
        self.assertTrue(valid_question("ぼくは濃度を先に見たんだ。そっちはどうして待ち時間を先にしたの？"))
        self.assertFalse(valid_question("いい質問ですね、待ち時間はどう考えますか？"))
        self.assertFalse(valid_question("待ち時間のルールを上に移してみましょう、どう思う？"))
        self.assertFalse(valid_question("B室が5分放置されるのはどうして？"))
        self.assertTrue(valid_question("B室が5分放置されるのはどうして？", allowed_numbers={"5"}))
        self.assertTrue(valid_question("1,500ppmの部屋を先にするのはなぜ？", allowed_numbers={"1500"}))

    def test_repeated_question_marks_are_collapsed(self):
        self.assertEqual(normalize_question("「どの情報を参照していますか？？」"), "どの情報を参照していますか？")
        self.assertTrue(valid_question(normalize_question("どの部屋を優先するか、決め手は何ですか？？")))


class PeerDialogueTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_first_problem_points_to_a_concrete_minute(self):
        self.assertIn("テストケース3", first_problem(goal_example_program("group_a")))
        self.assertIn("分目", first_problem(goal_example_program("group_a")))
        self.assertIsNone(first_problem(goal_example_program("group_b")))
        self.assertIn("すべて", plan_facts(goal_example_program("group_b")))

    def test_plans_are_served_only_on_request_and_only_known_ids(self):
        cards = self.client.get("/api/ventilation/plans", params={"ids": "group_a,group_c"}).json()
        self.assertEqual([card["id"] for card in cards], ["group_a", "group_c"])
        self.assertIn("program", cards[0])
        self.assertFalse(cards[0]["results"]["all_met"])
        self.assertEqual(self.client.get("/api/ventilation/plans", params={"ids": "learner"}).status_code, 422)

    def test_pair_partner_talks_about_a_difference_between_plans(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "fallback"}):
            body = {"program": goal_example_program("group_b").model_dump(), "phase": 2, "pair_plan": "group_a"}
            data = self.client.post("/api/ventilation/advice", json=body).json()
        self.assertIsNone(data["facts"])
        self.assertIn("違う", data["message"])
        differences = program_differences(goal_example_program("group_b"), goal_example_program("group_a"))
        self.assertIn(differences[0]["stage_name"], data["message"])

    def test_pair_partner_never_holds_the_plan_that_meets_every_case(self):
        body = {"program": Program().model_dump(), "phase": 2, "pair_plan": "group_b"}
        self.assertEqual(self.client.post("/api/ventilation/advice", json=body).status_code, 422)

    def test_choice_logs_keep_the_selected_plan_and_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("ventilation_service.LOG_FILE", Path(directory) / "logs.jsonl"):
                record = append_log(SessionLog(task_id="ventilation-goals-v3", program=Program(), session_id="s", event_id="c",
                                               event="choice", choice={"stage": "before", "plan": "group_c", "reason": "継続が大事"}))
        self.assertEqual(record["choice"]["plan"], "group_c")


class AllCasesTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def answer_program(self):
        program = example_program("complete").model_dump()
        program["selection"] = [rule("s_wait", "wait", condition("wait", 3, "gte")),
                                rule("s_urgent", "co2", condition("co2", 1500, "gte")),
                                rule("s_keep", "co2", condition("was_served")), rule("s_co2", "co2")]
        return program

    def test_runs_every_test_case_in_order(self):
        data = self.client.post("/api/ventilation/simulate-all", json={"program": self.answer_program()}).json()
        self.assertEqual([case["id"] for case in data["cases"]], [s["id"] for s in SCENARIOS])
        self.assertTrue(data["all_met"])
        self.assertEqual([case["minutes"] for case in data["cases"]], [len(s["steps"]) for s in SCENARIOS])

    def test_empty_program_and_urgent_first_fail_some_cases(self):
        empty = self.client.post("/api/ventilation/simulate-all", json={"program": Program().model_dump()}).json()
        self.assertFalse(empty["all_met"])
        urgent_first = example_program("complete").model_dump()
        data = self.client.post("/api/ventilation/simulate-all", json={"program": urgent_first}).json()
        failed = [case["id"] for case in data["cases"] if not case["goals_met"]]
        self.assertEqual(failed, ["urgent"])

    def test_run_all_log_keeps_server_computed_results(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("ventilation_service.LOG_FILE", Path(directory) / "logs.jsonl"):
                entry = SessionLog(task_id="ventilation-goals-v3", program=Program.model_validate(self.answer_program()),
                                   session_id="s", event_id="run-all", event="run_all", scenario_id="all")
                record = append_log(entry)
                self.assertTrue(record["test_cases"]["all_met"])
                self.assertEqual(len(record["test_cases"]["cases"]), len(SCENARIOS))
                step = append_log(SessionLog(task_id="ventilation-goals-v3", program=Program(), steps=[TestInput()],
                                             session_id="s", event_id="step", event="step"))
                self.assertNotIn("test_cases", step)


class NumericalGoalsTest(unittest.TestCase):
    def test_unserved_wait_four_is_allowed_but_five_is_not(self):
        steps = [TestInput(aCo2=1000, bCo2=700) for _ in range(5)]
        self.assertTrue(simulate(Program(), steps[:4])["achievement"]["all_met"])
        result = simulate(Program(), steps)
        self.assertFalse(result["achievement"]["all_met"])
        self.assertTrue(result["constraints_met"])

    def test_800_is_unnecessary_but_801_and_999_are_allowed(self):
        program = Program.model_validate({"demand": [rule("d", "on")], "selection": [rule("s", "room_a")], "output": [rule("o", "selected")]})
        for co2 in (800, 801, 999, 1000):
            result = simulate(program, [TestInput(aCo2=co2, bCo2=700)])
            self.assertEqual(result["metrics"]["unnecessary_ventilation_steps"], int(co2 <= 800))
            self.assertEqual(result["achievement"]["all_met"], co2 > 800)
        result = simulate(program, [TestInput(aCo2=700, aOccupied=False, bCo2=700)])
        self.assertEqual(result["metrics"]["unnecessary_ventilation_steps"], 1)  # No double count.

    def test_no_execution_has_no_achievement_result(self):
        result = simulate(Program(), [])
        self.assertIsNone(result["achievement"]["all_met"])
        self.assertTrue(all(c["met"] is None for c in result["achievement"]["checks"]))

    def test_different_solutions_can_meet_all_targets(self):
        program = example_program("complete").model_dump()
        program["selection"] = [rule("wait", "wait", condition("wait", 3, "gte")), rule("keep", "co2", condition("was_served")), rule("co2", "co2")]
        balanced = Program.model_validate(program)
        for scenario in SCENARIOS:
            steps = [TestInput.model_validate(s) for s in scenario["steps"]]
            self.assertTrue(simulate(balanced, steps)["achievement"]["all_met"], scenario["id"])
        steps = [TestInput(aCo2=1400, bCo2=1100) for _ in range(8)]
        waiting = simulate(goal_example_program("group_b"), steps)
        self.assertTrue(waiting["achievement"]["all_met"])
        self.assertNotEqual([r["after"]["output"] for r in waiting["trace"]],
                            [r["after"]["output"] for r in simulate(balanced, steps)["trace"]])

    def test_improvement_only_compares_identical_inputs_and_lengths(self):
        steps = [TestInput(aCo2=1500, bCo2=700)]
        baseline = SimulationBaseline(program=Program(), steps=steps)
        result = simulate(goal_example_program("group_a"), steps, baseline=baseline)
        self.assertTrue(result["comparison"]["reduced"])
        self.assertEqual(result["comparison"]["previous"], 1)
        self.assertEqual(result["comparison"]["current"], 0)
        self.assertFalse(simulate(Program(), steps * 2, baseline=baseline)["comparison"]["comparable"])
        self.assertFalse(simulate(Program(), [TestInput(aCo2=1501, bCo2=700)], baseline=baseline)["comparison"]["comparable"])

    def test_zero_baseline_is_not_claimed_as_reduction(self):
        steps = [TestInput(aCo2=700, bCo2=700)]
        comparison = simulate(Program(), steps, baseline=SimulationBaseline(program=Program(), steps=steps))["comparison"]
        self.assertTrue(comparison["already_zero"])
        self.assertFalse(comparison["reduced"])

    def test_v2_evaluation_is_retained_without_new_targets(self):
        result = simulate(Program(), [TestInput()], "ventilation-goals-v2")
        self.assertNotIn("achievement", result)
        self.assertNotIn("unnecessary_ventilation_steps", result["metrics"])


if __name__ == "__main__":
    unittest.main()
