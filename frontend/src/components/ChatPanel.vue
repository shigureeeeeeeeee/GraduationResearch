<script setup>
import { nextTick, ref } from 'vue'

const props = defineProps({
  visible: { type: Boolean, required: true },
  groupPhase: { type: Boolean, required: true },
  title: { type: String, required: true },
  description: { type: String, required: true },
  inputPlaceholder: { type: String, required: true },
  adviceLabel: { type: String, required: true },
  messages: { type: Array, required: true },
  loading: { type: Boolean, required: true },
  modelValue: { type: String, required: true },
  groupExamples: { type: Array, default: () => [] },
  groupDescription: { type: String, default: '各グループは下の案から考え始め、ほかの発言を聞いて考え直すこともあります。' },
  disabled: Boolean,
})

const emit = defineEmits(['update:modelValue', 'send', 'request-advice'])
const endRef = ref(null)

async function scrollToBottom() {
  await nextTick()
  endRef.value?.scrollIntoView({ behavior: 'smooth' })
}

function speakerName(message) {
  if (message.speaker) return message.speaker
  if (message.role === 'ai') return props.groupPhase ? '司会役' : 'ペア'
  return props.groupPhase ? '自分の意見' : 'あなた'
}

function handleKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    emit('send')
  }
}

defineExpose({ scrollToBottom })
</script>

<template>
  <section v-if="!visible" class="panel panel-chat-placeholder">
    <div class="placeholder-title">ペアとの対話</div>
    <div class="placeholder-text">
      まずは<strong>自分だけで</strong>プログラムを考えてみよう。<br>
      「次のフェーズへ進む」を押すと、同じ課題に取り組むペア（AI）と話せるようになるよ。
    </div>
  </section>

  <section v-else class="panel panel-chat">
    <h2 class="panel-title">{{ title }}</h2>
    <p class="panel-desc">{{ description }}</p>

    <div v-if="groupPhase && groupExamples.length" class="group-discussion-panel">
      <div class="group-panel-title">討論に参加する3つのAIグループ</div>
      <p class="group-panel-desc">{{ groupDescription }}</p>
      <div class="group-example-list">
        <div v-for="example in groupExamples" :key="example.group" class="group-example-card">
          <div class="group-example-header"><span class="group-badge">{{ example.group }}</span><strong>{{ example.title }}</strong></div>
          <div class="group-rule-list">
            <div v-for="ruleText in example.rules" :key="ruleText" class="group-rule-line">{{ ruleText }}</div>
          </div>
          <div class="group-question">{{ example.question }}</div>
        </div>
      </div>
    </div>

    <div class="chat-window">
      <template v-for="message in messages" :key="message.id">
        <!-- 実行結果などの事実はシステムが計算したもので、仲間の発言とは分けて示す -->
        <div v-if="message.role === 'system'" class="chat-facts">
          <span>{{ message.speaker || '実行結果' }}（システムが計算）</span>
          <p>{{ message.text }}</p>
        </div>
        <div
          v-else
          class="chat-bubble"
          :class="[
            message.role === 'ai' ? 'bubble-ai' : (message.role === 'group' ? 'bubble-group' : 'bubble-user'),
            message.agentId ? `bubble-${message.agentId}` : '',
          ]"
        >
          <div class="bubble-avatar">{{ speakerName(message) }}</div>
          <div class="bubble-text">{{ message.text }}<small v-if="message.llm?.fallback" class="fallback-label">ルールベースの補助応答</small></div>
        </div>
      </template>
      <div v-if="loading" class="chat-bubble bubble-ai loading-bubble">
        <div class="bubble-avatar">{{ groupPhase ? 'みんな' : 'ペア' }}</div>
        <div class="bubble-text">{{ groupPhase ? 'みんなが話しています' : '考え中' }}<span class="dots">...</span></div>
      </div>
      <div ref="endRef" />
    </div>

    <div class="chat-input-area">
      <textarea
        :value="modelValue"
        class="chat-input"
        :placeholder="inputPlaceholder"
        rows="2"
        maxlength="5000"
        :disabled="loading || disabled"
        @input="$emit('update:modelValue', $event.target.value)"
        @keydown="handleKeydown"
      />
      <button class="btn-send" :disabled="loading || disabled || !modelValue.trim()" @click="$emit('send')">送信</button>
    </div>
    <button class="btn-advice" :disabled="loading || disabled" @click="$emit('request-advice')">
      {{ loading ? '考え中...' : adviceLabel }}
    </button>
  </section>
</template>
