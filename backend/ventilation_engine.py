"""Deterministic learner interpreter and independent reference state machine."""
from copy import deepcopy
import operator

from ventilation_models import Program, TestInput

ROOMS = ("A", "B")
OUTPUT_LABELS = {"A": "A室を換気", "B": "B室を換気", "stop": "停止"}
COMPARISONS = {"eq": operator.eq, "ne": operator.ne, "gt": operator.gt,
               "gte": operator.ge, "lt": operator.lt, "lte": operator.le}


def initial_state():
    return {"demand": {"A": False, "B": False}, "wait": {"A": 0, "B": 0},
            "output": "stop", "run": 0}


def room_context(room, env, state):
    prefix = room.lower()
    return {"occupied": getattr(env, prefix + "Occupied"), "co2": getattr(env, prefix + "Co2"),
            "previous_demand": state["demand"][room], "wait": state["wait"][room],
            "was_served": state["output"] == room, "maintenance": env.maintenance}


def matches(rule, context):
    if not rule.conditions:
        return True
    results = []
    for condition in rule.conditions:
        right = context[condition.other_field] if condition.other_field else condition.value
        result = COMPARISONS[condition.op](context[condition.field], right)
        results.append(not result if condition.negate else result)
    return all(results) if rule.join == "all" else any(results)


def finish_step(state, env, demand, output):
    return {
        "demand": demand,
        "output": output,
        "run": 0 if output == "stop" else state["run"] + 1,
        "wait": {room: 0 if env.maintenance or not demand[room] or output == room
                 else state["wait"][room] + 1 for room in ROOMS},
    }


def learner_step(program: Program, env: TestInput, state):
    demand = {}
    fired = {"demand": {}, "selection": None, "output": None}
    contexts = {room: room_context(room, env, state) for room in ROOMS}
    for room in ROOMS:
        rule = next((rule for rule in program.demand if matches(rule, contexts[room])), None)
        demand[room] = bool(rule and (rule.action == "on" or (
            rule.action == "keep" and state["demand"][room])))
        fired["demand"][room] = rule.id if rule else None

    candidate = "stop"
    for rule in program.selection:
        rooms = [room for room in ROOMS if demand[room] and matches(rule, contexts[room])]
        if rule.action in ("room_a", "room_b"):
            rooms = [room for room in rooms if room == rule.action[-1].upper()]
        if not rooms:
            continue
        if rule.action == "wait":
            rooms.sort(key=lambda room: (-contexts[room]["wait"], -contexts[room]["co2"], room))
        else:
            rooms.sort(key=lambda room: (-contexts[room]["co2"], -contexts[room]["wait"], room))
        candidate = rooms[0]
        fired["selection"] = rule.id
        break

    context = {"maintenance": env.maintenance, "run": state["run"],
               "previous_output": state["output"], "candidate": candidate}
    rule = next((rule for rule in program.output if matches(rule, context)), None)
    output = candidate if rule and rule.action == "selected" else "stop"
    fired["output"] = rule.id if rule else None
    return finish_step(state, env, demand, output), candidate, fired


def reference_step(env: TestInput, state):
    """Specification oracle: deliberately independent of the learner rule language."""
    demand = {}
    co2 = {"A": env.aCo2, "B": env.bCo2}
    occupied = {"A": env.aOccupied, "B": env.bOccupied}
    for room in ROOMS:
        demand[room] = occupied[room] and (
            co2[room] >= 1000 or (state["demand"][room] and co2[room] > 800))
    output = "stop"
    eligible = [room for room in ROOMS if demand[room]]
    if not env.maintenance and state["run"] < 2 and eligible:
        urgent = [room for room in eligible if co2[room] >= 1500]
        waiting = [room for room in eligible if state["wait"][room] >= 3]
        if urgent:
            output = min(urgent, key=lambda room: (-co2[room], -state["wait"][room], room))
        elif waiting:
            output = min(waiting, key=lambda room: (-state["wait"][room], -co2[room], room))
        elif state["output"] in eligible:
            output = state["output"]
        else:
            output = min(eligible, key=lambda room: (-co2[room], -state["wait"][room], room))
        if state["output"] != "stop" and state["output"] != output:
            output = "stop"
    # Keep this update separate from the interpreter to detect implementation drift.
    return {"demand": demand, "output": output,
            "run": state["run"] + 1 if output != "stop" else 0,
            "wait": {room: state["wait"][room] + 1
                     if demand[room] and output != room and not env.maintenance else 0
                     for room in ROOMS}}


def compare_states(actual, expected):
    differences = []
    if actual["output"] != expected["output"]:
        differences.append("装置動作")
    for room in ROOMS:
        if actual["demand"][room] != expected["demand"][room]:
            differences.append(f"{room}室の換気要求")
        if actual["wait"][room] != expected["wait"][room]:
            differences.append(f"{room}室の待ち時間")
    if actual["run"] != expected["run"]:
        differences.append("連続運転数")
    return differences


def simulate_reference(program, steps):
    state, expected_state = initial_state(), initial_state()
    trace = []
    for index, env in enumerate(steps, 1):
        before = deepcopy(state)
        expected_before = deepcopy(expected_state)
        state, candidate, fired = learner_step(program, env, before)
        expected_state = reference_step(env, expected_before)
        differences = compare_states(state, expected_state)
        violations = []
        if state["output"] != "stop":
            if env.maintenance:
                violations.append("点検中に装置が動いています。")
            if before["run"] >= 2:
                violations.append("連続2ステップの運転後に停止していません。")
            if before["output"] not in ("stop", state["output"]):
                violations.append("部屋の切り替えに停止を挟んでいません。")
        trace.append({"step": index, "input": env.model_dump(), "before": before,
                      "after": deepcopy(state), "expected_before": expected_before,
                      "expected": deepcopy(expected_state), "candidate": candidate,
                      "fired": fired, "differences": differences, "violations": violations,
                      "ok": not differences})
    return {"trace": trace, "state": state, "expected_state": expected_state,
            "correct_steps": sum(row["ok"] for row in trace),
            "all_correct": bool(trace) and all(row["ok"] for row in trace)}


def simulate(program, steps, task_id="ventilation-goals-v3", baseline=None):
    """Observe constraints and goal indicators without prescribing a policy."""
    if task_id == "ventilation-v1":
        return simulate_reference(program, steps)
    state = initial_state()
    goal_wait = {room: 0 for room in ROOMS}
    metrics = {"violation_steps": 0, "needs_room_steps": 0, "served_room_steps": 0,
               "unserved_room_steps": 0, "urgent_unserved_room_steps": 0,
               "idle_with_need_steps": 0, "unoccupied_ventilation_steps": 0,
               "below_guidance_ventilation_steps": 0, "ventilation_steps": 0,
               "max_wait": {room: 0 for room in ROOMS}}
    numerical_goals = task_id == "ventilation-goals-v3"
    if numerical_goals:
        metrics["low_concentration_ventilation_steps"] = 0
    trace = []
    for index, env in enumerate(steps, 1):
        before = deepcopy(state)
        state, candidate, fired = learner_step(program, env, before)
        output = state["output"]
        violations = []
        if output != "stop":
            if env.maintenance:
                violations.append("点検中に装置が動いています。")
            if before["run"] >= 2:
                violations.append("連続2ステップの運転後に停止していません。")
            if before["output"] not in ("stop", output):
                violations.append("部屋の切り替えに停止を挟んでいません。")
            metrics["ventilation_steps"] += 1
            if not getattr(env, output.lower() + "Occupied"):
                metrics["unoccupied_ventilation_steps"] += 1
            elif getattr(env, output.lower() + "Co2") < 1000:
                metrics["below_guidance_ventilation_steps"] += 1
                if numerical_goals and getattr(env, output.lower() + "Co2") <= 800:
                    metrics["low_concentration_ventilation_steps"] += 1
        metrics["violation_steps"] += bool(violations)
        needs = {room: getattr(env, room.lower() + "Occupied") and
                 getattr(env, room.lower() + "Co2") >= 1000 for room in ROOMS}
        unserved, urgent = [], []
        for room in ROOMS:
            # Evaluation is independent of the learner's demand and wait fields.
            # Maintenance is unavailable time; invalid hardware commands earn no coverage.
            if env.maintenance or not needs[room]:
                goal_wait[room] = 0
                continue
            metrics["needs_room_steps"] += 1
            served = output == room and not violations
            metrics["served_room_steps"] += bool(served)
            goal_wait[room] = 0 if served else goal_wait[room] + 1
            metrics["max_wait"][room] = max(metrics["max_wait"][room], goal_wait[room])
            if not served:
                unserved.append(room)
                if getattr(env, room.lower() + "Co2") >= 1500:
                    urgent.append(room)
        metrics["unserved_room_steps"] += len(unserved)
        metrics["urgent_unserved_room_steps"] += len(urgent)
        if not env.maintenance and output == "stop" and any(needs.values()):
            metrics["idle_with_need_steps"] += 1
        observation = {"needs": needs, "unserved_rooms": unserved,
                       "urgent_unserved_rooms": urgent, "goal_wait": deepcopy(goal_wait),
                       "maintenance_excluded": env.maintenance}
        trace.append({"step": index, "input": env.model_dump(), "before": before,
                      "after": deepcopy(state), "candidate": candidate, "fired": fired,
                      "violations": violations, "constraints_met": not violations,
                      "observation": observation})
    result = {"task_id": task_id, "evaluation_mode": "goals_and_constraints",
            "trace": trace, "state": state, "metrics": metrics,
            "constraints_met": bool(trace) and metrics["violation_steps"] == 0}
    if numerical_goals:
        metrics["unnecessary_ventilation_steps"] = (metrics["unoccupied_ventilation_steps"] +
                                                    metrics["low_concentration_ventilation_steps"])
        checks = [
            {"id": "wait", "label": "連続未対応4ステップ以内", "actual": max(metrics["max_wait"].values()), "target": 4},
            {"id": "unnecessary", "label": "無人・800ppm以下への運転0回", "actual": metrics["unnecessary_ventilation_steps"], "target": 0},
            {"id": "constraints", "label": "装置の制約違反0回", "actual": metrics["violation_steps"], "target": 0},
        ]
        for check in checks:
            check["met"] = check["actual"] <= check["target"] if trace else None
        result["achievement"] = {"evaluated": bool(trace), "checks": checks,
                                 "all_met": all(check["met"] for check in checks) if trace else None}
        if baseline is not None:
            comparable = bool(steps) and [s.model_dump() for s in steps] == [s.model_dump() for s in baseline.steps]
            result["comparison"] = {"comparable": comparable}
            if comparable:
                previous = simulate(baseline.program, baseline.steps, task_id)
                old_value = previous["metrics"]["urgent_unserved_room_steps"]
                current = metrics["urgent_unserved_room_steps"]
                result["comparison"].update({"previous": old_value, "current": current,
                                             "reduced": current < old_value,
                                             "already_zero": old_value == current == 0})
    return result
