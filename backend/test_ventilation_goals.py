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
from ventilation_service import append_log, context_for


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
