<script setup>
import {
  ACTION_LABELS,
  ACTION_OPTIONS,
  CONDITION_LABELS,
  CONDITION_OPTIONS,
} from '../config'

defineProps({
  rules: { type: Array, required: true },
  aiDraft: { type: Array, required: true },
  showChat: { type: Boolean, required: true },
  awarenessMessage: { type: String, default: '' },
})

defineEmits([
  'add-rule',
  'remove-rule',
  'move-up',
  'move-down',
  'toggle-condition',
  'toggle-action',
  'apply-draft',
])

function hasCondition(rule, conditionType) {
  return rule.conditions.some((condition) => condition.type === conditionType)
}

function formatConditions(rule) {
  return rule.conditions
    .map((condition) => CONDITION_LABELS[condition.type] || condition.type)
    .join(' AND ')
}
</script>

<template>
  <section class="panel panel-builder">
    <div class="panel-title-row">
      <h2 class="panel-title">プログラム構築</h2>
      <span
        v-if="showChat && awarenessMessage"
        class="rule-aware-badge"
        :class="{ 'badge-loading': awarenessMessage.includes('中') }"
      >{{ awarenessMessage }}</span>
    </div>
    <p class="panel-desc">
      条件（センサー）とアクションを選んでルールを作ろう。<br>
      複数のルールが同時に発動することもあるよ。
    </p>

    <div class="rules-list">
      <div v-for="(rule, index) in rules" :key="rule.id" class="rule-card">
        <div class="rule-header">
          <span class="rule-number">ルール {{ index + 1 }}</span>
          <div class="rule-order-btns">
            <button class="btn-order" :disabled="index === 0" title="上へ" @click="$emit('move-up', index)">▲</button>
            <button class="btn-order" :disabled="index === rules.length - 1" title="下へ" @click="$emit('move-down', index)">▼</button>
          </div>
          <button class="btn-remove" title="削除" @click="$emit('remove-rule', rule.id)">×</button>
        </div>

        <div class="rule-body">
          <div class="cond-group">
            <span class="block-label">条件（AND でつながる）</span>
            <div class="cond-buttons">
              <button
                v-for="option in CONDITION_OPTIONS"
                :key="option.value"
                class="cond-toggle"
                :class="{ active: hasCondition(rule, option.value) }"
                @click="$emit('toggle-condition', rule, option.value)"
              >{{ option.label }}</button>
            </div>
            <div v-if="rule.conditions.length >= 2" class="and-hint">
              <span class="and-badge">AND</span><span class="and-hint-text">両方の条件が揃ったとき</span>
            </div>
          </div>
          <div class="arrow-block">→</div>
          <div class="action-group">
            <span class="block-label">アクション</span>
            <div class="action-buttons">
              <button
                v-for="option in ACTION_OPTIONS"
                :key="option.value"
                class="action-toggle"
                :class="{ active: rule.action === option.value }"
                @click="$emit('toggle-action', rule, option.value)"
              >{{ option.label }}</button>
            </div>
          </div>
        </div>
        <div v-if="rule.conditions.length === 0 || !rule.action" class="rule-warn">
          {{ rule.conditions.length === 0 ? '条件を選んでください' : 'アクションを選んでください' }}
        </div>
      </div>
      <div v-if="rules.length === 0" class="empty-hint">まだルールがありません。「＋ ルールを追加」から作り始めよう！</div>
    </div>

    <div v-if="aiDraft.length > 0" class="ai-draft-box">
      <div class="ai-draft-header">
        <span class="ai-draft-title">AIがこの問題で考えたプログラム</span>
        <button class="btn-apply-draft" @click="$emit('apply-draft')">この考えを反映</button>
      </div>
      <div class="ai-draft-list">
        <div v-for="(rule, index) in aiDraft" :key="`draft-${index}`" class="ai-draft-item">
          <span class="ai-draft-number">AI案 {{ index + 1 }}</span>
          <div class="ai-draft-flow">
            <span class="ai-draft-chip">{{ formatConditions(rule) }}</span>
            <span class="ai-draft-arrow">→</span>
            <span class="ai-draft-chip action">{{ ACTION_LABELS[rule.action] || rule.action }}</span>
          </div>
        </div>
      </div>
    </div>
    <button class="btn-add" @click="$emit('add-rule')">＋ ルールを追加</button>
  </section>
</template>
