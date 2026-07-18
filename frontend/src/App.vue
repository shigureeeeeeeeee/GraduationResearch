<script setup>
import { computed, ref, watch } from 'vue'
import ChatPanel from './components/ChatPanel.vue'
import PhaseBar from './components/PhaseBar.vue'
import RuleBuilder from './components/RuleBuilder.vue'
import SettingsDrawer from './components/SettingsDrawer.vue'
import SimulationPanel from './components/SimulationPanel.vue'
import { PHASE_INTRO_MESSAGES, PHASES } from './config'
import {
  evaluateAllScenarios,
  evaluateScenario,
} from './domain/simulation'
import {
  fetchAdvice,
  saveSessionLog,
  streamGroupDiscussion,
} from './services/api'

const sessionId = Date.now() + '-' + Math.random().toString(36).slice(2, 8)

const currentPhase = ref(1)
const currentPhaseData = computed(() => PHASES[currentPhase.value - 1])
const isGroupPhase = computed(() => currentPhase.value === 4)

const rules = ref([])
const aiProgramDraft = ref([])
const environment = ref({ personPresent: false, isDark: false })

const rulesForApi = computed(() =>
  rules.value.filter((rule) => rule.action && rule.conditions.length > 0),
)

const allScenarios = computed(() => evaluateAllScenarios(rulesForApi.value))
const allCorrect = computed(() => allScenarios.value.every((scenario) => scenario.ok))
const simResult = computed(() => {
  const result = evaluateScenario(rulesForApi.value, environment.value)
  return {
    doorOpen: result.doorOpen,
    bellRinging: result.bellRinging,
    doorCorrect: result.doorCorrect,
    bellCorrect: result.bellCorrect,
    allCorrect: false,
  }
})

const chatMessages = ref([
  {
    id: 0,
    role: 'ai',
    speaker: 'AI',
    phase: 1,
    text: 'こんにちは！コンビニの入り口プログラムを一緒に考えましょう。\nまずは「どんなときにドアが開いてほしいか」から考えてみてください。できたら「AIに話しかける」ボタンを押してね。',
  },
])
const userInput = ref('')
const isLoading = ref(false)
const chatPanelRef = ref(null)

const chatPanelTitle = computed(() =>
  isGroupPhase.value ? '全体対話' : 'AI との対話',
)
const chatPanelDesc = computed(() =>
  isGroupPhase.value
    ? '独立したA・B・Cグループの発言を聞き、司会AIと一緒に考えを比べよう。'
    : '考えたことや疑問をAIに話しかけてみよう。\nヒントをもらいながら一緒に考えられます。',
)
const chatInputPlaceholder = computed(() =>
  isGroupPhase.value
    ? '全体に共有したい意見を書く（Enterで送信、Shift+Enterで改行）'
    : 'AIに話しかける（Enterで送信、Shift+Enterで改行）',
)
const adviceButtonLabel = computed(() =>
  isGroupPhase.value
    ? 'A・B・Cグループの討論を進める'
    : '今のプログラムについてアドバイスをもらう',
)

async function scrollToBottom() {
  await chatPanelRef.value?.scrollToBottom()
}

async function saveLog(event, phase) {
  try {
    await saveSessionLog({
      session_id: sessionId,
      event,
      phase,
      rules: rulesForApi.value,
      chat_history: chatMessages.value
        .filter((message) => message.id !== 0)
        .map((message) => ({
          role: message.role,
          text: message.text,
          speaker: message.speaker,
        })),
      all_correct: allCorrect.value,
    })
  } catch {
    // ログ保存失敗は学習画面の操作を妨げない。
  }
}

async function advancePhase() {
  if (currentPhase.value >= PHASES.length) return
  await saveLog('phase_complete', currentPhase.value)
  const nextPhase = currentPhase.value + 1
  currentPhase.value = nextPhase
  const intro = PHASE_INTRO_MESSAGES[nextPhase]
  if (intro) {
    chatMessages.value.push({
      id: Date.now(),
      role: 'ai',
      speaker: nextPhase === 4 ? '司会AI' : 'AI',
      phase: nextPhase,
      text: intro,
    })
    await scrollToBottom()
  }
}

async function completeSession() {
  await saveLog('session_end', PHASES.length)
}

function addRule() {
  rules.value.push({
    id: Date.now().toString(),
    conditions: [],
    action: '',
  })
}

function removeRule(id) {
  rules.value = rules.value.filter((rule) => rule.id !== id)
}

function moveRule(index, offset) {
  const destination = index + offset
  if (destination < 0 || destination >= rules.value.length) return
  const reordered = [...rules.value]
  ;[reordered[index], reordered[destination]] = [
    reordered[destination],
    reordered[index],
  ]
  rules.value = reordered
}

function toggleCondition(rule, conditionType) {
  const index = rule.conditions.findIndex(
    (condition) => condition.type === conditionType,
  )
  if (index >= 0) {
    rule.conditions.splice(index, 1)
  } else {
    rule.conditions.push({ type: conditionType })
  }
}

function toggleAction(rule, action) {
  rule.action = rule.action === action ? '' : action
}

function normalizeDraftRule(rule) {
  if (!rule || !Array.isArray(rule.conditions) || !rule.action) return null
  const conditionTypes = rule.conditions
    .map((condition) => condition?.type)
    .filter((type) => type === 'person_sensor' || type === 'dark_sensor')
  if (conditionTypes.length === 0) return null
  if (rule.action !== 'door' && rule.action !== 'bell') return null
  return {
    conditions: conditionTypes.map((type) => ({ type })),
    action: rule.action,
  }
}

function updateAiProgramDraft(data) {
  if (!data || !Array.isArray(data.program_draft)) return
  aiProgramDraft.value = data.program_draft
    .map(normalizeDraftRule)
    .filter(Boolean)
}

function applyAiDraftToRules() {
  if (aiProgramDraft.value.length === 0) return
  rules.value = aiProgramDraft.value.map((rule, index) => ({
    id: Date.now() + '-' + index,
    conditions: rule.conditions.map((condition) => ({ type: condition.type })),
    action: rule.action,
  }))
}

function updateEnvironment(values) {
  Object.assign(environment.value, values)
}

function historyForApi({ phase4Only = false } = {}) {
  return chatMessages.value
    .filter(
      (message) =>
        message.id !== 0 && (!phase4Only || message.phase === 4),
    )
    .map((message) => ({
      role: message.role,
      text: message.text,
      speaker: message.speaker,
    }))
}

function buildAdvicePayload(currentMessage, history) {
  return {
    rules: rulesForApi.value,
    environment: environment.value,
    result: { ...simResult.value, allCorrect: allCorrect.value },
    history,
    current_message: currentMessage,
    phase: currentPhase.value,
  }
}

async function callAdviceApi(
  currentMessage,
  history = historyForApi(),
) {
  return fetchAdvice(buildAdvicePayload(currentMessage, history))
}

async function callGroupDiscussionApi(
  currentMessage,
  history = historyForApi({ phase4Only: true }),
) {
  const payload = buildAdvicePayload(currentMessage, history)
  payload.phase = 4
  await streamGroupDiscussion(payload, async (turn) => {
    chatMessages.value.push({
      id: Date.now() + '-' + turn.agent_id + '-' + chatMessages.value.length,
      role: turn.role,
      speaker: turn.speaker,
      agentId: turn.agent_id,
      phase: 4,
      text: turn.text,
    })
    await scrollToBottom()
  })
}

function appendConnectionError(text) {
  chatMessages.value.push({
    id: Date.now() + 1,
    role: 'ai',
    text,
  })
}

async function sendMessage() {
  const text = userInput.value.trim()
  if (!text || isLoading.value) return

  const history = historyForApi({ phase4Only: isGroupPhase.value })
  chatMessages.value.push({
    id: Date.now(),
    role: 'user',
    speaker: isGroupPhase.value ? '自分の意見' : 'あなた',
    phase: currentPhase.value,
    text,
  })
  userInput.value = ''
  await scrollToBottom()

  isLoading.value = true
  try {
    if (isGroupPhase.value) {
      await callGroupDiscussionApi(text, history)
    } else {
      const data = await callAdviceApi(text, history)
      updateAiProgramDraft(data)
      chatMessages.value.push({
        id: Date.now() + 1,
        role: 'ai',
        speaker: 'AI',
        phase: currentPhase.value,
        text: data.message,
      })
    }
  } catch {
    appendConnectionError(
      'バックエンドに接続できませんでした。サーバーが起動しているか確認してください。',
    )
  } finally {
    isLoading.value = false
    await scrollToBottom()
  }
}

async function requestAdvice() {
  if (isLoading.value) return
  isLoading.value = true
  try {
    if (isGroupPhase.value) {
      await callGroupDiscussionApi(null)
    } else {
      const data = await callAdviceApi(null)
      updateAiProgramDraft(data)
      chatMessages.value.push({
        id: Date.now(),
        role: 'ai',
        speaker: 'AI',
        phase: currentPhase.value,
        text: data.message,
      })
    }
  } catch {
    appendConnectionError('バックエンドに接続できませんでした。')
  } finally {
    isLoading.value = false
    await scrollToBottom()
  }
}

const ruleAwareMsg = ref('')
let autoAdviceTimer = null
let autoAdviceRunning = false

watch(
  rulesForApi,
  () => {
    if (!currentPhaseData.value.showChat || isGroupPhase.value) return

    ruleAwareMsg.value = 'ルールを認識中...'
    clearTimeout(autoAdviceTimer)
    autoAdviceTimer = setTimeout(async () => {
      if (isLoading.value || autoAdviceRunning) return

      autoAdviceRunning = true
      ruleAwareMsg.value = 'ルールをAIに送信中...'
      isLoading.value = true
      try {
        const data = await callAdviceApi('プログラムを更新したよ。')
        updateAiProgramDraft(data)
        chatMessages.value.push({
          id: Date.now(),
          role: 'ai',
          text: data.message,
        })
        ruleAwareMsg.value = 'AIがルールを認識しています'
      } catch {
        ruleAwareMsg.value = 'AI接続エラー'
      } finally {
        isLoading.value = false
        autoAdviceRunning = false
        await scrollToBottom()
      }
    }, 1500)
  },
  { deep: true },
)
</script>

<template>
  <div class="app">
    <SettingsDrawer />

    <div class="problem-banner">
      <div class="problem-inner">
        <span class="problem-label">課題</span>
        <span class="problem-text">
          人が来たら<strong>自動ドアを開ける</strong>、
          夜に人が来たら<strong>チャイムを鳴らす</strong>プログラムを作ろう。
        </span>
      </div>
    </div>

    <PhaseBar
      :phases="PHASES"
      :current-phase="currentPhase"
      :current-phase-data="currentPhaseData"
      @advance="advancePhase"
      @complete="completeSession"
    />

    <main class="main-grid" :class="{ 'no-chat': !currentPhaseData.showChat }">
      <RuleBuilder
        :rules="rules"
        :ai-draft="aiProgramDraft"
        :show-chat="currentPhaseData.showChat"
        :awareness-message="ruleAwareMsg"
        @add-rule="addRule"
        @remove-rule="removeRule"
        @move-up="moveRule($event, -1)"
        @move-down="moveRule($event, 1)"
        @toggle-condition="toggleCondition"
        @toggle-action="toggleAction"
        @apply-draft="applyAiDraftToRules"
      />

      <SimulationPanel
        :environment="environment"
        :result="simResult"
        :scenarios="allScenarios"
        @select-environment="updateEnvironment"
      />

      <ChatPanel
        ref="chatPanelRef"
        v-model="userInput"
        :visible="currentPhaseData.showChat"
        :group-phase="isGroupPhase"
        :title="chatPanelTitle"
        :description="chatPanelDesc"
        :input-placeholder="chatInputPlaceholder"
        :advice-label="adviceButtonLabel"
        :messages="chatMessages"
        :loading="isLoading"
        @send="sendMessage"
        @request-advice="requestAdvice"
      />
    </main>
  </div>
</template>
