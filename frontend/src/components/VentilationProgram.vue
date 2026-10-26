<script setup>
import { ref } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true },
  config: { type: Object, required: true },
  latest: { type: Object, default: null },
  disabled: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const operators = [
  { value: 'eq', label: '＝' }, { value: 'ne', label: '≠' },
  { value: 'gte', label: '以上 ≥' }, { value: 'gt', label: 'より大きい >' },
  { value: 'lte', label: '以下 ≤' }, { value: 'lt', label: 'より小さい <' },
]
const opSymbol = { eq: '＝', ne: '≠', gte: '≥', gt: '>', lte: '≤', lt: '<' }
const outputs = [{ value: 'A', label: 'A室' }, { value: 'B', label: 'B室' }, { value: 'stop', label: '停止' }]
// 各段階の役割と、次の段階へ渡すもの
const STAGE_GUIDE = {
  demand: { title: '各部屋が「換気してほしい」か決める', next: '要求がONの部屋が、次の段階の候補になります' },
  selection: { title: '候補の中から、換気する部屋を1つ選ぶ', next: '選んだ部屋を、次の段階で装置に命令するか決めます' },
  output: { title: '装置の制限を確かめ、実際の動作を決める', next: '' },
}
const outputLabel = (value) => ({ A: 'A室', B: 'B室', stop: '停止' }[value])
const clone = (value) => JSON.parse(JSON.stringify(value))
const kind = (field) => props.config.fields[field].kind
const collapsed = ref({})
const editing = ref({})

function mutate(stageId, edit) {
  const program = clone(props.modelValue)
  edit(program[stageId])
  emit('update:modelValue', program)
}
function stageOf(stageId) {
  return props.config.stages.find((item) => item.id === stageId)
}
function newCondition(stage, field = stage.fields[0]) {
  const defaults = { co2: 1000, wait: 3, run: 2 }
  return { field, op: kind(field) === 'number' ? 'gte' : 'eq', value: kind(field) === 'boolean' ? true : kind(field) === 'output' ? 'stop' : defaults[field] || 0, negate: false }
}
function addRule(stage) {
  // 条件なしのルールは常に一致してしまうため、条件を1つ置いた状態で追加する
  const id = crypto.randomUUID()
  editing.value[id] = true
  mutate(stage.id, (list) => list.push({ id, join: 'all', conditions: [newCondition(stage)], action: stage.actions[0].value }))
}
function setRule(stageId, index, key, value) {
  mutate(stageId, (list) => { list[index][key] = value })
}
function setCondition(stage, index, conditionIndex, key, value) {
  mutate(stage.id, (list) => {
    const condition = list[index].conditions[conditionIndex]
    if (key === 'field') list[index].conditions[conditionIndex] = newCondition(stage, value)
    else if (key === 'other_field') {
      if (value) condition.other_field = value
      else delete condition.other_field
    } else condition[key] = value
  })
}
function changeValue(stage, index, conditionIndex, value) {
  const type = kind(props.modelValue[stage.id][index].conditions[conditionIndex].field)
  const number = Number(value)
  const bounded = Number.isFinite(number) ? Math.min(10000, Math.max(0, number)) : 0
  setCondition(stage, index, conditionIndex, 'value', type === 'number' ? bounded : type === 'boolean' ? value === 'true' : value)
}
function move(stageId, index, offset) {
  mutate(stageId, (list) => { [list[index], list[index + offset]] = [list[index + offset], list[index]] })
}
function comparableFields(stage, field) {
  return stage.fields.filter((other) => other !== field && kind(field) === kind(other))
}

function conditionText(condition) {
  const label = props.config.fields[condition.field].label
  const other = condition.other_field && props.config.fields[condition.other_field].label
  let text
  if (kind(condition.field) === 'boolean' && !other) {
    text = (condition.value === true) === (condition.op === 'eq') ? label : `${label}（いいえ）`
  } else if (kind(condition.field) === 'output') {
    text = `${label}${condition.op === 'eq' ? ' ＝ ' : ' ≠ '}${other || outputLabel(condition.value)}`
  } else {
    text = `${label} ${opSymbol[condition.op]} ${other || condition.value}`
  }
  return condition.negate ? `NOT（${text}）` : text
}
function ruleSummary(stage, rule) {
  const action = stage.actions.find((item) => item.value === rule.action)?.label || ''
  const joiner = rule.join === 'all' ? ' かつ ' : ' または '
  const conditions = rule.conditions.map(conditionText).join(joiner)
  if (stage.id === 'selection') {
    return rule.conditions.length ? `要求ONの部屋のうち、${conditions} の部屋があれば → ${action}` : `要求ONの部屋があれば → ${action}`
  }
  if (!rule.conditions.length) return `いつでも → ${action}`
  return `もし ${conditions} なら → ${action}`
}

// 直前の1分で、どのルールが使われ、各段階が何を決めたか
function firedRooms(stageId, ruleId) {
  if (!props.latest) return []
  if (stageId === 'demand') return ['A', 'B'].filter((room) => props.latest.fired.demand[room] === ruleId)
  return props.latest.fired[stageId] === ruleId ? ['used'] : []
}
function stageResult(stageId) {
  const row = props.latest
  if (!row) return ''
  if (stageId === 'demand') return `A室 ${row.after.demand.A ? 'ON' : 'OFF'} ／ B室 ${row.after.demand.B ? 'ON' : 'OFF'}`
  if (stageId === 'selection') return `候補：${outputLabel(row.candidate)}`
  return `動作：${row.after.output === 'stop' ? '停止' : `${row.after.output}室を換気`}`
}
// 既定動作が使われた場合の説明。①は部屋ごとに判定する
function defaultUsedText(stageId) {
  if (!props.latest) return ''
  if (stageId === 'demand') {
    const rooms = ['A', 'B'].filter((room) => !props.latest.fired.demand[room])
    return rooms.length ? `${props.latest.step}分目の${rooms.join('・')}室ではこれが使われました` : ''
  }
  return props.latest.fired[stageId] ? '' : `${props.latest.step}分目ではこれが使われました`
}
</script>

<template>
  <section class="panel panel-builder program-editor">
    <div class="panel-title-row">
      <h2 class="panel-title">プログラム</h2>
      <span class="lab-muted small">{{ Object.values(modelValue).flat().length }} ルール</span>
    </div>
    <p class="panel-desc">1分ごとに、①→②→③の順に判断します。各段階では<strong>上から順に</strong>条件を調べ、最初に当てはまったルールだけを使います。</p>
    <p v-if="latest" class="lab-muted small fired-legend"><span class="fired-chip">使用</span> は {{ latest.step }}分目に使われたルールです。</p>
    <div class="program-flow">
      <template v-for="(stage, stageIndex) in config.stages" :key="stage.id">
        <section class="stage-block" :class="{ collapsed: collapsed[stage.id] }">
          <button type="button" class="stage-header" :aria-expanded="!collapsed[stage.id]" @click="collapsed[stage.id] = !collapsed[stage.id]">
            <span class="stage-number">{{ ['①', '②', '③'][stageIndex] }}</span>
            <span class="stage-title"><strong>{{ stage.label }}</strong><small>{{ STAGE_GUIDE[stage.id].title }}</small></span>
            <span class="stage-count">{{ modelValue[stage.id].length }}</span>
            <span class="stage-toggle" aria-hidden="true">{{ collapsed[stage.id] ? '▸' : '▾' }}</span>
          </button>
          <p v-if="latest" class="stage-result">{{ latest.step }}分目の結果　<strong>{{ stageResult(stage.id) }}</strong></p>
          <fieldset v-show="!collapsed[stage.id]" :disabled="disabled" class="program-fieldset stage-content">
            <p class="stage-description">{{ stage.description }}</p>
            <div v-for="(rule, index) in modelValue[stage.id]" :key="rule.id" class="rule-card program-rule" :class="{ fired: firedRooms(stage.id, rule.id).length }">
              <div class="rule-header">
                <strong class="rule-number">ルール {{ index + 1 }}</strong>
                <span v-if="firedRooms(stage.id, rule.id).length" class="fired-chip">使用{{ stage.id === 'demand' ? `（${firedRooms(stage.id, rule.id).join('・')}室）` : '' }}</span>
                <div class="rule-order-btns">
                  <button type="button" class="btn-order" :disabled="index === 0" :aria-label="`ルール${index + 1}を上へ`" @click="move(stage.id, index, -1)">↑</button>
                  <button type="button" class="btn-order" :disabled="index === modelValue[stage.id].length - 1" :aria-label="`ルール${index + 1}を下へ`" @click="move(stage.id, index, 1)">↓</button>
                  <button type="button" class="btn-remove" :aria-label="`ルール${index + 1}を削除`" @click="mutate(stage.id, (list) => list.splice(index, 1))">×</button>
                </div>
              </div>
              <p class="rule-summary">{{ ruleSummary(stage, rule) }}</p>
              <button type="button" class="text-button rule-edit-toggle" :aria-expanded="!!editing[rule.id]" @click="editing[rule.id] = !editing[rule.id]">{{ editing[rule.id] ? '編集を閉じる' : '条件と動作を編集' }}</button>
              <div v-if="editing[rule.id]" class="rule-edit">
                <div class="condition-heading">
                  <span>もし</span>
                  <select :value="rule.join" aria-label="条件の組み合わせ" @change="setRule(stage.id, index, 'join', $event.target.value)">
                    <option value="all">すべての条件（AND）</option><option value="any">いずれかの条件（OR）</option>
                  </select>
                </div>
                <p v-if="rule.conditions.length === 0" class="empty-condition">条件なし：いつでも一致します</p>
                <div v-for="(condition, ci) in rule.conditions" :key="ci" class="condition-editor">
                  <div class="condition-top">
                    <select :value="condition.field" aria-label="調べる値" @change="setCondition(stage, index, ci, 'field', $event.target.value)">
                      <option v-for="field in stage.fields" :key="field" :value="field">{{ config.fields[field].label }}</option>
                    </select>
                    <button type="button" class="btn-remove" aria-label="条件を削除" @click="mutate(stage.id, (list) => list[index].conditions.splice(ci, 1))">×</button>
                  </div>
                  <div class="condition-comparison">
                    <select :value="condition.op" aria-label="比較方法" @change="setCondition(stage, index, ci, 'op', $event.target.value)">
                      <option v-for="op in operators.filter((item) => kind(condition.field) === 'number' || ['eq', 'ne'].includes(item.value))" :key="op.value" :value="op.value">{{ op.label }}</option>
                    </select>
                    <select v-if="comparableFields(stage, condition.field).length" :value="condition.other_field || ''" aria-label="比較する相手" @change="setCondition(stage, index, ci, 'other_field', $event.target.value)">
                      <option value="">指定した値</option>
                      <option v-for="field in comparableFields(stage, condition.field)" :key="field" :value="field">{{ config.fields[field].label }}</option>
                    </select>
                    <template v-if="!condition.other_field">
                      <input v-if="kind(condition.field) === 'number'" type="number" min="0" max="10000" :value="condition.value" aria-label="比較する数値" @change="changeValue(stage, index, ci, $event.target.value)">
                      <select v-else-if="kind(condition.field) === 'boolean'" :value="String(condition.value)" aria-label="比較する真偽値" @change="changeValue(stage, index, ci, $event.target.value)">
                        <option value="true">はい / ON</option><option value="false">いいえ / OFF</option>
                      </select>
                      <select v-else :value="condition.value" aria-label="比較する動作" @change="changeValue(stage, index, ci, $event.target.value)">
                        <option v-for="output in outputs" :key="output.value" :value="output.value">{{ output.label }}</option>
                      </select>
                    </template>
                  </div>
                  <label class="negate-label"><input type="checkbox" :checked="condition.negate" @change="setCondition(stage, index, ci, 'negate', $event.target.checked)">この条件を否定する（NOT）</label>
                </div>
                <button v-if="rule.conditions.length < 12" type="button" class="text-button" @click="mutate(stage.id, (list) => list[index].conditions.push(newCondition(stage)))">＋ 条件を追加</button>
                <label class="action-editor"><span>なら</span>
                  <select :value="rule.action" aria-label="実行する動作" @change="setRule(stage.id, index, 'action', $event.target.value)">
                    <option v-for="action in stage.actions" :key="action.value" :value="action.value">{{ action.label }}</option>
                  </select>
                </label>
              </div>
            </div>
            <p class="stage-default" :class="{ 'default-used': defaultUsedText(stage.id) }">{{ stage.default }}<template v-if="defaultUsedText(stage.id)">（{{ defaultUsedText(stage.id) }}）</template></p>
            <button type="button" class="btn-add add-program-rule" :disabled="modelValue[stage.id].length >= 30" @click="addRule(stage)">＋ {{ stage.label }}のルールを追加</button>
          </fieldset>
        </section>
        <p v-if="STAGE_GUIDE[stage.id].next" class="stage-arrow"><span aria-hidden="true">↓</span>{{ STAGE_GUIDE[stage.id].next }}</p>
      </template>
    </div>
    <p class="lab-muted small">プログラムを変更すると実行は初期状態に戻ります。変更前の実行と修正理由はログに残ります。</p>
  </section>
</template>
