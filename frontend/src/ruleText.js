// ルールを日本語の一文にする。backend/ventilation_describe.py と同じ言い回しにそろえる
const OP_SYMBOLS = { eq: '＝', ne: '≠', gte: '≥', gt: '>', lte: '≤', lt: '<' }
const OUTPUT_NAMES = { A: 'A室', B: 'B室', stop: '停止' }
export const STAGE_NAMES = { demand: '①換気要求', selection: '②部屋の選択', output: '③装置への命令' }

export function conditionText(config, condition) {
  const label = config.fields[condition.field].label
  const kind = config.fields[condition.field].kind
  const other = condition.other_field && config.fields[condition.other_field].label
  let text
  if (kind === 'boolean' && !other) {
    text = (condition.value === true) === (condition.op === 'eq') ? label : `${label}（いいえ）`
  } else if (kind === 'output') {
    text = `${label}${condition.op === 'eq' ? ' ＝ ' : ' ≠ '}${other || OUTPUT_NAMES[condition.value]}`
  } else {
    text = `${label} ${OP_SYMBOLS[condition.op]} ${other || condition.value}`
  }
  return condition.negate ? `NOT（${text}）` : text
}

export function ruleSummary(config, stage, rule) {
  const action = stage.actions.find((item) => item.value === rule.action)?.label || rule.action
  const joiner = rule.join === 'all' ? ' かつ ' : ' または '
  const conditions = rule.conditions.map((condition) => conditionText(config, condition)).join(joiner)
  if (stage.id === 'selection') {
    return rule.conditions.length ? `要求ONの部屋のうち、${conditions} の部屋があれば → ${action}` : `要求ONの部屋があれば → ${action}`
  }
  if (!rule.conditions.length) return `いつでも → ${action}`
  return `もし ${conditions} なら → ${action}`
}

// 段階ごとの要約。比較では順番も意味を持つので、並びが違えば「違う」とみなす
export function programSummary(config, program) {
  return config.stages.map((stage) => ({ id: stage.id, name: STAGE_NAMES[stage.id], rules: (program[stage.id] || []).map((rule) => ruleSummary(config, stage, rule)) }))
}

export function compareSummaries(mine, theirs) {
  return mine.map((stage, index) => {
    const other = theirs[index]
    const same = stage.rules.length === other.rules.length && stage.rules.every((text, i) => text === other.rules[i])
    return { id: stage.id, name: stage.name, same,
      mine: stage.rules.map((text) => ({ text, shared: other.rules.includes(text) })),
      theirs: other.rules.map((text) => ({ text, shared: stage.rules.includes(text) })) }
  })
}
