<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true },
  config: { type: Object, required: true },
  disabled: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const activeStage = ref('demand')
const stage = computed(() => props.config.stages.find((item) => item.id === activeStage.value))
const rules = computed(() => props.modelValue[activeStage.value])
const operators = [
  { value: 'eq', label: '＝' }, { value: 'ne', label: '≠' },
  { value: 'gte', label: '以上 ≥' }, { value: 'gt', label: 'より大きい >' },
  { value: 'lte', label: '以下 ≤' }, { value: 'lt', label: 'より小さい <' },
]
const outputs = [{ value: 'A', label: 'A室' }, { value: 'B', label: 'B室' }, { value: 'stop', label: '停止' }]
const clone = (value) => JSON.parse(JSON.stringify(value))
const kind = (field) => props.config.fields[field].kind

function mutate(edit) {
  const program = clone(props.modelValue)
  edit(program[activeStage.value])
  emit('update:modelValue', program)
}
function newCondition(field = stage.value.fields[0]) {
  const defaults = { co2: 1000, wait: 3, run: 2 }
  return { field, op: 'eq', value: kind(field) === 'boolean' ? true : kind(field) === 'output' ? 'stop' : defaults[field] || 0, negate: false }
}
function addRule() {
  mutate((list) => list.push({ id: crypto.randomUUID(), join: 'all', conditions: [], action: stage.value.actions[0].value }))
}
function setRule(index, key, value) {
  mutate((list) => { list[index][key] = value })
}
function setCondition(index, conditionIndex, key, value) {
  mutate((list) => {
    const condition = list[index].conditions[conditionIndex]
    if (key === 'field') list[index].conditions[conditionIndex] = newCondition(value)
    else if (key === 'other_field') {
      if (value) condition.other_field = value
      else delete condition.other_field
    } else condition[key] = value
  })
}
function changeValue(index, conditionIndex, value) {
  const type = kind(rules.value[index].conditions[conditionIndex].field)
  const number = Number(value)
  const bounded = Number.isFinite(number) ? Math.min(10000, Math.max(0, number)) : 0
  setCondition(index, conditionIndex, 'value', type === 'number' ? bounded : type === 'boolean' ? value === 'true' : value)
}
function move(index, offset) {
  mutate((list) => { [list[index], list[index + offset]] = [list[index + offset], list[index]] })
}
function comparableFields(field) {
  return stage.value.fields.filter((other) => other !== field && kind(field) === kind(other))
}
</script>

<template>
  <section class="panel panel-builder program-editor">
    <div class="panel-title-row">
      <h2 class="panel-title">プログラム構築</h2>
      <span class="lab-muted small">{{ Object.values(modelValue).flat().length }} ルール</span>
    </div>
    <p class="panel-desc">各段階で、上から最初に一致したルールを使います。</p>
    <div class="program-tabs" role="tablist" aria-label="プログラムの段階">
      <button v-for="(item, index) in config.stages" :key="item.id" type="button" role="tab" class="env-btn"
        :aria-selected="activeStage === item.id" :class="{ active: activeStage === item.id }" @click="activeStage = item.id">
        <span>{{ index + 1 }}</span>{{ item.label }}<small>{{ modelValue[item.id].length }}</small>
      </button>
    </div>
    <p class="stage-description">{{ stage.description }}</p>
    <fieldset :disabled="disabled" class="program-fieldset">
      <div v-for="(rule, index) in rules" :key="rule.id" class="rule-card program-rule">
        <div class="rule-header">
          <strong class="rule-number">ルール {{ index + 1 }}</strong>
          <div class="rule-order-btns">
            <button type="button" class="btn-order" :disabled="index === 0" :aria-label="`ルール${index + 1}を上へ`" @click="move(index, -1)">↑</button>
            <button type="button" class="btn-order" :disabled="index === rules.length - 1" :aria-label="`ルール${index + 1}を下へ`" @click="move(index, 1)">↓</button>
            <button type="button" class="btn-remove" :aria-label="`ルール${index + 1}を削除`" @click="mutate((list) => list.splice(index, 1))">×</button>
          </div>
        </div>
        <div class="condition-heading">
          <span>もし</span>
          <select :value="rule.join" aria-label="条件の組み合わせ" @change="setRule(index, 'join', $event.target.value)">
            <option value="all">すべての条件（AND）</option><option value="any">いずれかの条件（OR）</option>
          </select>
        </div>
        <p v-if="rule.conditions.length === 0" class="empty-condition">条件なし：いつでも一致します</p>
        <div v-for="(condition, ci) in rule.conditions" :key="ci" class="condition-editor">
          <div class="condition-top">
            <select :value="condition.field" aria-label="調べる値" @change="setCondition(index, ci, 'field', $event.target.value)">
              <option v-for="field in stage.fields" :key="field" :value="field">{{ config.fields[field].label }}</option>
            </select>
            <button type="button" class="btn-remove" aria-label="条件を削除" @click="mutate((list) => list[index].conditions.splice(ci, 1))">×</button>
          </div>
          <div class="condition-comparison">
            <select :value="condition.op" aria-label="比較方法" @change="setCondition(index, ci, 'op', $event.target.value)">
              <option v-for="op in operators.filter((item) => kind(condition.field) === 'number' || ['eq', 'ne'].includes(item.value))" :key="op.value" :value="op.value">{{ op.label }}</option>
            </select>
            <select v-if="comparableFields(condition.field).length" :value="condition.other_field || ''" aria-label="比較する相手" @change="setCondition(index, ci, 'other_field', $event.target.value)">
              <option value="">指定した値</option>
              <option v-for="field in comparableFields(condition.field)" :key="field" :value="field">{{ config.fields[field].label }}</option>
            </select>
            <template v-if="!condition.other_field">
              <input v-if="kind(condition.field) === 'number'" type="number" min="0" max="10000" :value="condition.value" aria-label="比較する数値" @change="changeValue(index, ci, $event.target.value)">
              <select v-else-if="kind(condition.field) === 'boolean'" :value="String(condition.value)" aria-label="比較する真偽値" @change="changeValue(index, ci, $event.target.value)">
                <option value="true">ON / はい</option><option value="false">OFF / いいえ</option>
              </select>
              <select v-else :value="condition.value" aria-label="比較する動作" @change="changeValue(index, ci, $event.target.value)">
                <option v-for="output in outputs" :key="output.value" :value="output.value">{{ output.label }}</option>
              </select>
            </template>
          </div>
          <label class="negate-label"><input type="checkbox" :checked="condition.negate" @change="setCondition(index, ci, 'negate', $event.target.checked)">この条件を否定する（NOT）</label>
        </div>
        <button v-if="rule.conditions.length < 12" type="button" class="text-button" @click="mutate((list) => list[index].conditions.push(newCondition()))">＋ 条件を追加</button>
        <label class="action-editor"><span>なら</span>
          <select :value="rule.action" aria-label="実行する動作" @change="setRule(index, 'action', $event.target.value)">
            <option v-for="action in stage.actions" :key="action.value" :value="action.value">{{ action.label }}</option>
          </select>
        </label>
      </div>
      <div v-if="!rules.length" class="empty-hint">この段階のルールを作ってみよう。<br>条件と動作を選び、必要な順番に並べます。</div>
      <button type="button" class="btn-add add-program-rule" :disabled="rules.length >= 30" @click="addRule">＋ {{ stage.label }}のルールを追加</button>
    </fieldset>
    <p class="stage-default">{{ stage.default }}</p>
    <p class="lab-muted small">プログラムを変更すると実行は初期状態に戻ります。変更前の実行と修正理由はログに残ります。</p>
  </section>
</template>
