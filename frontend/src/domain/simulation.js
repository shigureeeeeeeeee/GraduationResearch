import { SCENARIOS } from '../config'

export function evaluateRules(rules, personPresent, isDark) {
  const conditionValues = { person_sensor: personPresent, dark_sensor: isDark }
  let doorOpen = false
  let bellRinging = false

  for (const rule of rules) {
    const matches = rule.conditions.length > 0
      && rule.conditions.every((condition) => conditionValues[condition.type] ?? false)
    if (!matches) continue
    if (rule.action === 'door') doorOpen = true
    if (rule.action === 'bell') bellRinging = true
  }
  return { doorOpen, bellRinging }
}

export function expectedResult(personPresent, isDark) {
  return {
    doorOpen: personPresent,
    bellRinging: personPresent && isDark,
  }
}

export function evaluateScenario(rules, scenario) {
  const result = evaluateRules(rules, scenario.personPresent, scenario.isDark)
  const expected = expectedResult(scenario.personPresent, scenario.isDark)
  const doorCorrect = result.doorOpen === expected.doorOpen
  const bellCorrect = result.bellRinging === expected.bellRinging
  return {
    ...scenario,
    ...result,
    doorCorrect,
    bellCorrect,
    ok: doorCorrect && bellCorrect,
  }
}

export function evaluateAllScenarios(rules) {
  return SCENARIOS.map((scenario) => evaluateScenario(rules, scenario))
}
