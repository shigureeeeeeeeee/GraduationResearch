<script setup>
import { ref, computed, nextTick, reactive, watch } from 'vue'

// ─────────────────────────────────────────────
// セッション管理
// ─────────────────────────────────────────────
const sessionId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

async function saveLog(event, phase) {
  try {
    await fetch('http://localhost:8001/api/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        event,
        phase,
        rules: rulesForApi.value,
        chat_history: chatMessages.value
          .filter((m) => m.id !== 0)
          .map((m) => ({ role: m.role, text: m.text, speaker: m.speaker })),
        all_correct: allCorrect.value,
      }),
    })
  } catch {
    // ログ保存失敗は無視（メイン機能に影響させない）
  }
}

// ─────────────────────────────────────────────
// 実験者設定（プロンプト編集）
// ─────────────────────────────────────────────
const settingsOpen = ref(false)
const settingsSaving = ref(false)
const settingsMsg = ref('')
const settingsTab = ref('prompts')
const dashboardLoading = ref(false)
const dashboardMsg = ref('')
const logEntries = ref([])
const prompts = reactive({
  base: '',
  phase2_extra: '',
  phase3_extra: '',
  phase4_extra: '',
})
const PHASE_PROMPT_LABELS = [
  { key: 'base', label: '共通ベースプロンプト' },
  { key: 'phase2_extra', label: 'フェーズ2「ペアで対話」追加指示' },
  { key: 'phase3_extra', label: 'フェーズ3「実行して確認」追加指示' },
  { key: 'phase4_extra', label: 'フェーズ4「全体で対話」追加指示' },
]

async function openSettings() {
  settingsOpen.value = true
  settingsMsg.value = ''
  dashboardMsg.value = ''
  try {
    const res = await fetch('http://localhost:8001/api/config/prompts')
    const data = await res.json()
    Object.assign(prompts, data)
    await loadDashboard()
  } catch {
    settingsMsg.value = 'プロンプト設定の読み込みに失敗しました'
  }
}

async function loadDashboard() {
  dashboardLoading.value = true
  dashboardMsg.value = ''
  try {
    const res = await fetch('http://localhost:8001/api/log/export')
    logEntries.value = await res.json()
  } catch {
    dashboardMsg.value = 'ログの読み込みに失敗しました'
  } finally {
    dashboardLoading.value = false
  }
}

const sessionRows = computed(() => {
  const bySession = new Map()
  for (const entry of logEntries.value) {
    const current = bySession.get(entry.session_id)
    if (!current || new Date(entry.timestamp) > new Date(current.timestamp)) {
      bySession.set(entry.session_id, entry)
    }
  }
  return [...bySession.values()]
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .map((entry) => {
      const chatCount = (entry.chat_history || []).length
      const userChatCount = (entry.chat_history || []).filter((m) => m.role === 'user').length
      return {
        ...entry,
        shortId: entry.session_id.slice(-8),
        finished: entry.event === 'session_end',
        ruleCount: (entry.rules || []).length,
        chatCount,
        userChatCount,
        timestampLabel: new Date(entry.timestamp).toLocaleString('ja-JP'),
      }
    })
})

const dashboardSummary = computed(() => {
  const rows = sessionRows.value
  const total = rows.length
  const completed = rows.filter((r) => r.finished).length
  const allCorrect = rows.filter((r) => r.all_correct).length
  const avgChat = total
    ? (rows.reduce((sum, r) => sum + r.chatCount, 0) / total).toFixed(1)
    : '0.0'
  return { total, completed, allCorrect, avgChat }
})

function downloadLogJson() {
  const blob = new Blob([JSON.stringify(logEntries.value, null, 2)], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `experiment-logs-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function escapeCsvValue(value) {
  const text = value == null ? '' : String(value)
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

function downloadLogCsv() {
  const headers = [
    'session_id',
    'final_phase',
    'finished',
    'all_correct',
    'rule_count',
    'chat_count',
    'user_chat_count',
    'last_saved_at',
  ]
  const rows = sessionRows.value.map((row) => [
    row.session_id,
    row.phase,
    row.finished,
    row.all_correct,
    row.ruleCount,
    row.chatCount,
    row.userChatCount,
    row.timestamp,
  ])
  const csv = [headers, ...rows]
    .map((row) => row.map((cell) => escapeCsvValue(cell)).join(','))
    .join('\n')
  const blob = new Blob([`\uFEFF${csv}`], {
    type: 'text/csv;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `experiment-summary-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

async function saveSettings() {
  settingsSaving.value = true
  settingsMsg.value = ''
  try {
    const res = await fetch('http://localhost:8001/api/config/prompts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...prompts }),
    })
    const data = await res.json()
    if (data.status === 'ok') {
      settingsMsg.value = '保存しました'
    }
  } catch {
    settingsMsg.value = '保存に失敗しました'
  } finally {
    settingsSaving.value = false
  }
}

async function resetSettings() {
  if (!confirm('プロンプトをデフォルトに戻しますか？')) return
  settingsSaving.value = true
  try {
    await fetch('http://localhost:8001/api/config/prompts/reset', { method: 'POST' })
    await openSettings()
    settingsMsg.value = 'デフォルトに戻しました'
  } catch {
    settingsMsg.value = 'リセットに失敗しました'
  } finally {
    settingsSaving.value = false
  }
}

// ─────────────────────────────────────────────
// フェーズ管理
// ─────────────────────────────────────────────
const PHASES = [
  {
    id: 1,
    label: '1人で考える',
    desc: 'まずは自分でプログラムを組み立ててみよう。センサーとアクションを組み合わせてルールを作ってください。',
    showChat: false,
  },
  {
    id: 2,
    label: 'ペアで対話する',
    desc: 'AIをペアの友達として、お互いのプログラムについて話し合おう。「なぜそうしたの？」を伝え合ってみよう。',
    showChat: true,
  },
  {
    id: 3,
    label: '実行して確認する',
    desc: '4つのシナリオ（昼夜×人あり/なし）を全部シミュレーションして、正しく動くか確認しよう。',
    showChat: true,
  },
  {
    id: 4,
    label: '全体で対話する',
    desc: '他のグループの考えを見ながら、クラス全体で「どこがよいか・どこを直せそうか」を話し合おう。',
    showChat: true,
  },
]

const currentPhase = ref(1)
const currentPhaseData = computed(() => PHASES[currentPhase.value - 1])
const isGroupPhase = computed(() => currentPhase.value === 4)

const PHASE_INTRO_MESSAGES = {
  2: 'こんにちは！ペアの対話フェーズだね。\nあなたのプログラム、どんなルールにした？私のと比べてみたいな。教えてくれる？',
  3: '実行して確認するフェーズだよ！\n4つの場面（昼・人あり、昼・人なし、夜・人あり、夜・人なし）を全部チェックしてみよう。全部✓になるかな？',
  4: 'ここからは全体対話だよ。\nA・B・Cの各AIグループが、それぞれの立場から順番に意見を出します。前のグループの発言も読みながら話し合うので、自分の考えも伝えて比べてみよう。',
}

const GROUP_DISCUSSION_EXAMPLES = [
  {
    group: 'Aグループ',
    title: '夜ならいつでもチャイム',
    rules: ['[明るさセンサーON（夜）] → [チャイムを鳴らす]'],
    question: '夜に人が来ていないときも、チャイムは鳴ってよいかな？',
  },
  {
    group: 'Bグループ',
    title: '夜だけドアが開く',
    rules: ['[人感センサーON AND 明るさセンサーON（夜）] → [ドアを開ける]'],
    question: '昼に人が来たとき、ドアはどうなるだろう？',
  },
  {
    group: 'Cグループ',
    title: 'ドアとチャイムを同じ条件にする',
    rules: [
      '[人感センサーON] → [ドアを開ける]',
      '[人感センサーON] → [チャイムを鳴らす]',
    ],
    question: '昼に人が来たとき、チャイムまで鳴る必要はあるかな？',
  },
]

const chatPanelTitle = computed(() =>
  isGroupPhase.value ? '全体対話' : 'AI との対話'
)

const chatPanelDesc = computed(() =>
  isGroupPhase.value
    ? '独立したA・B・Cグループの発言を聞き、司会AIと一緒に考えを比べよう。'
    : '考えたことや疑問をAIに話しかけてみよう。\nヒントをもらいながら一緒に考えられます。'
)

const chatInputPlaceholder = computed(() =>
  isGroupPhase.value
    ? '全体に共有したい意見を書く（Enterで送信、Shift+Enterで改行）'
    : 'AIに話しかける（Enterで送信、Shift+Enterで改行）'
)

const adviceButtonLabel = computed(() =>
  isGroupPhase.value
    ? 'A・B・Cグループの討論を進める'
    : '今のプログラムについてアドバイスをもらう'
)

async function advancePhase() {
  if (currentPhase.value >= 4) return
  // 現フェーズの状態を保存してから進む
  await saveLog('phase_complete', currentPhase.value)
  const next = currentPhase.value + 1
  currentPhase.value = next
  if (PHASE_INTRO_MESSAGES[next]) {
    chatMessages.value.push({
      id: Date.now(),
      role: 'ai',
      speaker: next === 4 ? '司会AI' : 'AI',
      phase: next,
      text: PHASE_INTRO_MESSAGES[next],
    })
    nextTick(() => chatEndRef.value?.scrollIntoView({ behavior: 'smooth' }))
  }
}

async function completeSession() {
  await saveLog('session_end', 4)
}

// ─────────────────────────────────────────────
// 定数
// ─────────────────────────────────────────────
const CONDITION_OPTIONS = [
  { value: 'person_sensor', label: '人感センサーON（人がいる）' },
  { value: 'dark_sensor',   label: '明るさセンサーON（夜・暗い）' },
]

const ACTION_OPTIONS = [
  { value: 'door', label: 'ドアを開ける' },
  { value: 'bell', label: 'チャイムを鳴らす' },
]

// 確認する全シナリオ
const SCENARIOS = [
  { label: '昼・人あり', personPresent: true,  isDark: false },
  { label: '昼・人なし', personPresent: false, isDark: false },
  { label: '夜・人あり', personPresent: true,  isDark: true  },
  { label: '夜・人なし', personPresent: false, isDark: true  },
]

// ─────────────────────────────────────────────
// プログラム構築
// ─────────────────────────────────────────────
const rules = ref([])
const aiProgramDraft = ref([])

const conditionLabelMap = {
  person_sensor: '人感センサーON（人がいる）',
  dark_sensor: '明るさセンサーON（夜・暗い）',
}

const actionLabelMap = {
  door: 'ドアを開ける',
  bell: 'チャイムを鳴らす',
}

function addRule() {
  rules.value.push({
    id: Date.now().toString(),
    conditions: [],
    action: '',
  })
}

function removeRule(id) {
  rules.value = rules.value.filter((r) => r.id !== id)
}

function moveUp(index) {
  if (index === 0) return
  const arr = [...rules.value]
  ;[arr[index - 1], arr[index]] = [arr[index], arr[index - 1]]
  rules.value = arr
}

function moveDown(index) {
  if (index === rules.value.length - 1) return
  const arr = [...rules.value]
  ;[arr[index], arr[index + 1]] = [arr[index + 1], arr[index]]
  rules.value = arr
}

function toggleCondition(rule, condType) {
  const idx = rule.conditions.findIndex((c) => c.type === condType)
  if (idx >= 0) {
    rule.conditions.splice(idx, 1)
  } else {
    rule.conditions.push({ type: condType })
  }
}

function hasCondition(rule, condType) {
  return rule.conditions.some((c) => c.type === condType)
}

function normalizeDraftRule(rule) {
  if (!rule || !Array.isArray(rule.conditions) || !rule.action) return null
  const normalizedConditions = rule.conditions
    .map((c) => c?.type)
    .filter((t) => t === 'person_sensor' || t === 'dark_sensor')
  if (normalizedConditions.length === 0) return null
  if (rule.action !== 'door' && rule.action !== 'bell') return null
  return {
    conditions: normalizedConditions.map((type) => ({ type })),
    action: rule.action,
  }
}

function updateAiProgramDraft(data) {
  if (!data || !Array.isArray(data.program_draft)) return
  aiProgramDraft.value = data.program_draft
    .map((r) => normalizeDraftRule(r))
    .filter(Boolean)
}

function formatDraftConditions(rule) {
  return rule.conditions
    .map((c) => conditionLabelMap[c.type] || c.type)
    .join(' AND ')
}

function applyAiDraftToRules() {
  if (aiProgramDraft.value.length === 0) return
  rules.value = aiProgramDraft.value.map((r, idx) => ({
    id: `${Date.now()}-${idx}`,
    conditions: r.conditions.map((c) => ({ type: c.type })),
    action: r.action,
  }))
}

// API 送信用フォーマット
const rulesForApi = computed(() =>
  rules.value.filter((r) => r.action && r.conditions.length > 0)
)

// ─────────────────────────────────────────────
// シミュレーション
// ─────────────────────────────────────────────
const env = ref({ personPresent: false, isDark: false })

function evaluate(ruleList, personPresent, isDark) {
  const conds = { person_sensor: personPresent, dark_sensor: isDark }
  let doorOpen = false
  let bellRinging = false
  for (const rule of ruleList) {
    if (
      rule.conditions.length > 0 &&
      rule.conditions.every((c) => conds[c.type] ?? false)
    ) {
      if (rule.action === 'door') doorOpen = true
      if (rule.action === 'bell') bellRinging = true
    }
  }
  return { doorOpen, bellRinging }
}

function correctResult(personPresent, isDark) {
  return {
    doorOpen: personPresent,
    bellRinging: personPresent && isDark,
  }
}

const simResult = computed(() => {
  const { personPresent, isDark } = env.value
  const { doorOpen, bellRinging } = evaluate(rulesForApi.value, personPresent, isDark)
  const correct = correctResult(personPresent, isDark)
  return {
    doorOpen,
    bellRinging,
    doorCorrect: doorOpen === correct.doorOpen,
    bellCorrect: bellRinging === correct.bellRinging,
    allCorrect: false, // filled below
  }
})

const allScenarios = computed(() =>
  SCENARIOS.map((s) => {
    const { doorOpen, bellRinging } = evaluate(rulesForApi.value, s.personPresent, s.isDark)
    const correct = correctResult(s.personPresent, s.isDark)
    return {
      ...s,
      doorOpen,
      bellRinging,
      doorCorrect: doorOpen === correct.doorOpen,
      bellCorrect: bellRinging === correct.bellRinging,
      ok: doorOpen === correct.doorOpen && bellRinging === correct.bellRinging,
    }
  })
)

const allCorrect = computed(() => allScenarios.value.every((s) => s.ok))

// ─────────────────────────────────────────────
// AI チャット
// ─────────────────────────────────────────────
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
const chatEndRef = ref(null)

async function scrollToBottom() {
  await nextTick()
  chatEndRef.value?.scrollIntoView({ behavior: 'smooth' })
}

function historyForApi({ phase4Only = false } = {}) {
  return chatMessages.value
    .filter((m) => m.id !== 0 && (!phase4Only || m.phase === 4))
    .map((m) => ({ role: m.role, text: m.text, speaker: m.speaker }))
}

// フェーズ2・3の通常AI API
async function callAdviceApi(currentMessage, history = historyForApi()) {
  const r = simResult.value

  const res = await fetch('http://localhost:8001/api/advice', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      rules: rulesForApi.value,
      environment: env.value,
      result: { ...r, allCorrect: allCorrect.value },
      history,
      current_message: currentMessage,
      phase: currentPhase.value,
    }),
  })
  if (!res.ok) throw new Error(`advice API: ${res.status}`)
  return res.json()
}

// フェーズ4: A・B・C・司会を別々のOllama呼び出しで動かす
async function callGroupDiscussionApi(currentMessage, history = historyForApi({ phase4Only: true })) {
  const r = simResult.value
  const res = await fetch('http://localhost:8001/api/group-discussion/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      rules: rulesForApi.value,
      environment: env.value,
      result: { ...r, allCorrect: allCorrect.value },
      history,
      current_message: currentMessage,
      phase: 4,
    }),
  })
  if (!res.ok) throw new Error(`group discussion API: ${res.status}`)

  if (!res.body) throw new Error('group discussion stream is unavailable')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const appendLine = async (line) => {
    if (!line.trim()) return
    const turn = JSON.parse(line)
    chatMessages.value.push({
      id: `${Date.now()}-${turn.agent_id}-${chatMessages.value.length}`,
      role: turn.role,
      speaker: turn.speaker,
      agentId: turn.agent_id,
      phase: 4,
      text: turn.text,
    })
    await scrollToBottom()
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) await appendLine(line)
    if (done) break
  }
  await appendLine(buffer)
}

function messageSpeaker(msg) {
  if (msg.speaker) return msg.speaker
  if (msg.role === 'ai') return isGroupPhase.value ? '司会AI' : 'AI'
  return isGroupPhase.value ? '自分の意見' : 'あなた'
}

async function sendMessage() {
  const text = userInput.value.trim()
  if (!text || isLoading.value) return

  // APIに渡す履歴は、今回の発言を追加する前に確定する
  const history = historyForApi({ phase4Only: isGroupPhase.value })

  // 先に表示に追加してから API 呼び出し
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
    chatMessages.value.push({
      id: Date.now() + 1,
      role: 'ai',
      text: 'バックエンドに接続できませんでした。サーバーが起動しているか確認してください。',
    })
  } finally {
    isLoading.value = false
    await scrollToBottom()
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

async function requestAdvice() {
  if (isLoading.value) return
  isLoading.value = true
  try {
    if (isGroupPhase.value) {
      await callGroupDiscussionApi(null)
    } else {
      // current_message なし → バックエンドがアドバイスリクエストとして処理
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
    chatMessages.value.push({
      id: Date.now(),
      role: 'ai',
      text: 'バックエンドに接続できませんでした。',
    })
  } finally {
    isLoading.value = false
    await scrollToBottom()
  }
}

// ─────────────────────────────────────────────
// ルール変更の自動検知 → AIが自動でコメント
// ─────────────────────────────────────────────
const ruleAwareMsg = ref('')
let autoAdviceTimer = null
let autoAdviceRunning = false  // 重複防止フラグ

watch(
  rulesForApi,
  () => {
    if (!currentPhaseData.value.showChat) return
    // フェーズ4は1回で4生成するため、明示的な討論操作だけで呼び出す
    if (isGroupPhase.value) return

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
        chatMessages.value.push({ id: Date.now(), role: 'ai', text: data.message })
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
  { deep: true }
)
</script>

<template>
  <div class="app">
    <!-- 実験者設定ボタン -->
    <button class="settings-fab" @click="openSettings" title="実験者設定">&#9881;</button>

    <!-- 設定ドロワー -->
    <transition name="drawer">
      <div v-if="settingsOpen" class="settings-overlay" @click.self="settingsOpen = false">
        <div class="settings-drawer">
          <div class="settings-header">
            <h2 class="settings-title">実験者設定</h2>
            <button class="settings-close" @click="settingsOpen = false">×</button>
          </div>
          <div class="settings-tabs">
            <button
              class="settings-tab"
              :class="{ active: settingsTab === 'prompts' }"
              @click="settingsTab = 'prompts'"
            >
              AIプロンプト
            </button>
            <button
              class="settings-tab"
              :class="{ active: settingsTab === 'dashboard' }"
              @click="settingsTab = 'dashboard'; loadDashboard()"
            >
              ログダッシュボード
            </button>
          </div>
          <p class="settings-note">
            <template v-if="settingsTab === 'prompts'">
              ここで編集したプロンプトはバックエンドに保存され、次のAI応答から反映されます。
            </template>
            <template v-else>
              保存された実験ログから、セッション数や正解状況、AIとの会話数を確認できます。
            </template>
          </p>

          <div v-if="settingsTab === 'prompts'" class="settings-body">
            <div
              v-for="item in PHASE_PROMPT_LABELS"
              :key="item.key"
              class="prompt-block"
            >
              <label class="prompt-label">{{ item.label }}</label>
              <textarea
                v-model="prompts[item.key]"
                class="prompt-textarea"
                rows="8"
                spellcheck="false"
              />
            </div>
          </div>

          <div v-else class="settings-body dashboard-body">
            <div class="dashboard-actions">
              <button class="btn-reset-prompt" @click="loadDashboard" :disabled="dashboardLoading">
                {{ dashboardLoading ? '読み込み中...' : '再読み込み' }}
              </button>
              <button class="btn-save-prompt" @click="downloadLogJson" :disabled="logEntries.length === 0">
                JSONをダウンロード
              </button>
              <button class="btn-save-prompt" @click="downloadLogCsv" :disabled="sessionRows.length === 0">
                CSVをダウンロード
              </button>
            </div>

            <div v-if="dashboardMsg" class="dashboard-error">{{ dashboardMsg }}</div>

            <div class="dashboard-summary-grid">
              <div class="dashboard-card">
                <span class="dashboard-card-label">セッション数</span>
                <strong>{{ dashboardSummary.total }}</strong>
              </div>
              <div class="dashboard-card">
                <span class="dashboard-card-label">完了セッション</span>
                <strong>{{ dashboardSummary.completed }}</strong>
              </div>
              <div class="dashboard-card">
                <span class="dashboard-card-label">全シナリオ正解</span>
                <strong>{{ dashboardSummary.allCorrect }}</strong>
              </div>
              <div class="dashboard-card">
                <span class="dashboard-card-label">平均会話数</span>
                <strong>{{ dashboardSummary.avgChat }}</strong>
              </div>
            </div>

            <div v-if="sessionRows.length === 0" class="dashboard-empty">
              まだ保存されたログがありません。フェーズ移動またはセッション完了時にログが保存されます。
            </div>

            <div v-else class="dashboard-table-wrap">
              <table class="dashboard-table">
                <thead>
                  <tr>
                    <th>セッション</th>
                    <th>最終フェーズ</th>
                    <th>状態</th>
                    <th>正解</th>
                    <th>ルール</th>
                    <th>会話</th>
                    <th>最終保存</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in sessionRows" :key="row.session_id">
                    <td>#{{ row.shortId }}</td>
                    <td>{{ row.phase }}</td>
                    <td>{{ row.finished ? '完了' : '途中' }}</td>
                    <td>
                      <span :class="row.all_correct ? 'dash-ok' : 'dash-ng'">
                        {{ row.all_correct ? '正解' : '未達' }}
                      </span>
                    </td>
                    <td>{{ row.ruleCount }}</td>
                    <td>{{ row.chatCount }}</td>
                    <td>{{ row.timestampLabel }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="settingsTab === 'prompts'" class="settings-footer">
            <span v-if="settingsMsg" class="settings-msg">{{ settingsMsg }}</span>
            <button class="btn-reset-prompt" @click="resetSettings" :disabled="settingsSaving">
              デフォルトに戻す
            </button>
            <button class="btn-save-prompt" @click="saveSettings" :disabled="settingsSaving">
              {{ settingsSaving ? '保存中...' : '保存する' }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 課題バナー -->
    <div class="problem-banner">
      <div class="problem-inner">
        <span class="problem-label">課題</span>
        <span class="problem-text">
          人が来たら<strong>自動ドアを開ける</strong>、
          夜に人が来たら<strong>チャイムを鳴らす</strong>プログラムを作ろう。
        </span>
      </div>
    </div>

    <!-- フェーズステッパー -->
    <div class="phase-bar">
      <div class="phase-bar-inner">
        <div class="phase-steps">
          <div
            v-for="p in PHASES"
            :key="p.id"
            class="phase-step"
            :class="{
              'step-done': p.id < currentPhase,
              'step-active': p.id === currentPhase,
              'step-future': p.id > currentPhase,
            }"
          >
            <div class="step-circle">
              <span v-if="p.id < currentPhase" class="step-check">✓</span>
              <span v-else>{{ p.id }}</span>
            </div>
            <div class="step-label">{{ p.label }}</div>
            <div v-if="p.id < PHASES.length" class="step-connector" />
          </div>
        </div>
        <div class="phase-desc">{{ currentPhaseData.desc }}</div>
        <div class="phase-nav">
          <button
            v-if="currentPhase < 4"
            class="btn-next-phase"
            @click="advancePhase"
          >
            次のフェーズへ進む →
          </button>
          <button
            v-else
            class="btn-next-phase btn-complete"
            @click="completeSession"
          >
            セッションを完了して保存する
          </button>
        </div>
      </div>
    </div>

    <main class="main-grid" :class="{ 'no-chat': !currentPhaseData.showChat }">
      <!-- ① プログラム構築 -->
      <section class="panel panel-builder">
        <div class="panel-title-row">
          <h2 class="panel-title">プログラム構築</h2>
          <span
            v-if="currentPhaseData.showChat && ruleAwareMsg"
            class="rule-aware-badge"
            :class="{ 'badge-loading': ruleAwareMsg.includes('中') }"
          >{{ ruleAwareMsg }}</span>
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
                <button class="btn-order" :disabled="index === 0" @click="moveUp(index)" title="上へ">▲</button>
                <button class="btn-order" :disabled="index === rules.length - 1" @click="moveDown(index)" title="下へ">▼</button>
              </div>
              <button class="btn-remove" @click="removeRule(rule.id)" title="削除">×</button>
            </div>

            <div class="rule-body">
              <!-- 条件選択（トグルボタン） -->
              <div class="cond-group">
                <span class="block-label">条件（AND でつながる）</span>
                <div class="cond-buttons">
                  <button
                    v-for="opt in CONDITION_OPTIONS"
                    :key="opt.value"
                    class="cond-toggle"
                    :class="{ active: hasCondition(rule, opt.value) }"
                    @click="toggleCondition(rule, opt.value)"
                  >
                    {{ opt.label }}
                  </button>
                </div>
                <div v-if="rule.conditions.length >= 2" class="and-hint">
                  <span class="and-badge">AND</span>
                  <span class="and-hint-text">両方の条件が揃ったとき</span>
                </div>
              </div>

              <div class="arrow-block">→</div>

              <!-- アクション選択 -->
              <div class="action-group">
                <span class="block-label">アクション</span>
                <div class="action-buttons">
                  <button
                    v-for="opt in ACTION_OPTIONS"
                    :key="opt.value"
                    class="action-toggle"
                    :class="{ active: rule.action === opt.value }"
                    @click="rule.action = (rule.action === opt.value ? '' : opt.value)"
                  >
                    {{ opt.label }}
                  </button>
                </div>
              </div>
            </div>

            <!-- 未完成警告 -->
            <div v-if="rule.conditions.length === 0 || !rule.action" class="rule-warn">
              {{ rule.conditions.length === 0 ? '条件を選んでください' : 'アクションを選んでください' }}
            </div>
          </div>

          <div v-if="rules.length === 0" class="empty-hint">
            まだルールがありません。「＋ ルールを追加」から作り始めよう！
          </div>
        </div>

        <div v-if="aiProgramDraft.length > 0" class="ai-draft-box">
          <div class="ai-draft-header">
            <span class="ai-draft-title">AIがこの問題で考えたプログラム</span>
            <button class="btn-apply-draft" @click="applyAiDraftToRules">
              この考えを反映
            </button>
          </div>
          <div class="ai-draft-list">
            <div
              v-for="(rule, idx) in aiProgramDraft"
              :key="`draft-${idx}`"
              class="ai-draft-item"
            >
              <span class="ai-draft-number">AI案 {{ idx + 1 }}</span>
              <div class="ai-draft-flow">
                <span class="ai-draft-chip">{{ formatDraftConditions(rule) }}</span>
                <span class="ai-draft-arrow">→</span>
                <span class="ai-draft-chip action">{{ actionLabelMap[rule.action] || rule.action }}</span>
              </div>
            </div>
          </div>
        </div>

        <button class="btn-add" @click="addRule">＋ ルールを追加</button>
      </section>

      <!-- ② シミュレーション -->
      <section class="panel panel-sim">
        <h2 class="panel-title">シミュレーション</h2>
        <p class="panel-desc">環境を選んで、プログラムの動きを確かめよう。</p>

        <!-- 環境選択 -->
        <div class="env-selector">
          <div class="env-row">
            <span class="env-label">時間帯</span>
            <div class="env-buttons">
              <button
                class="env-btn"
                :class="{ active: !env.isDark }"
                @click="env.isDark = false"
              >昼</button>
              <button
                class="env-btn"
                :class="{ active: env.isDark }"
                @click="env.isDark = true"
              >夜</button>
            </div>
          </div>
          <div class="env-row">
            <span class="env-label">人の有無</span>
            <div class="env-buttons">
              <button
                class="env-btn"
                :class="{ active: env.personPresent }"
                @click="env.personPresent = true"
              >人あり</button>
              <button
                class="env-btn"
                :class="{ active: !env.personPresent }"
                @click="env.personPresent = false"
              >人なし</button>
            </div>
          </div>
        </div>

        <!-- ビジュアルシーン -->
        <div class="sim-scene" :class="env.isDark ? 'scene-night' : 'scene-day'">

          <!-- 空 -->
          <div class="scene-sky">
            <div v-if="!env.isDark" class="sun"></div>
            <template v-else>
              <div class="star" v-for="i in 6" :key="i" :style="{ left: (10 + i * 14) + '%', top: (8 + (i % 3) * 12) + '%' }"></div>
            </template>
          </div>

          <!-- 地面 -->
          <div class="scene-ground"></div>

          <!-- 店舗 -->
          <div class="store-building">
            <!-- チャイム -->
            <div class="store-bell-wrap">
              <div class="store-bell" :class="{ 'bell-ringing': simResult.bellRinging }">
                <div class="bell-top"></div>
                <div class="bell-body-shape"></div>
                <div class="bell-clapper"></div>
              </div>
              <div v-if="simResult.bellRinging" class="bell-wave">♪</div>
            </div>

            <!-- 店舗看板 -->
            <div class="store-sign-bar">STORE</div>

            <!-- 自動ドア（スライド） -->
            <div class="door-frame">
              <div class="door-panel door-left" :class="{ 'door-open': simResult.doorOpen }"></div>
              <div class="door-panel door-right" :class="{ 'door-open': simResult.doorOpen }"></div>
              <div class="door-floor"></div>
            </div>
          </div>

          <!-- 人物 -->
          <transition name="person-slide">
            <div v-if="env.personPresent" class="person-figure">
              <div class="person-head"></div>
              <div class="person-body"></div>
              <div class="person-legs">
                <div class="leg left"></div>
                <div class="leg right"></div>
              </div>
            </div>
          </transition>
        </div>

        <!-- 全シナリオ表（クリックで切替） -->
        <div class="scenario-wrap">
          <p class="env-group-label">シナリオ切替</p>
          <table class="scenario-table">
            <thead>
              <tr>
                <th>状況</th>
                <th>ドア</th>
                <th>チャイム</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="s in allScenarios"
                :key="s.label"
                :class="{ 'row-active': s.personPresent === env.personPresent && s.isDark === env.isDark }"
                @click="env.personPresent = s.personPresent; env.isDark = s.isDark"
                style="cursor:pointer"
              >
                <td>{{ s.label }}</td>
                <td>{{ s.doorOpen ? '開' : '閉' }}</td>
                <td>{{ s.bellRinging ? '鳴る' : '静か' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- フェーズ1：AI非表示のプレースホルダー -->
      <section v-if="!currentPhaseData.showChat" class="panel panel-chat-placeholder">
        <div class="placeholder-title">AI との対話</div>
        <div class="placeholder-text">
          まずは<strong>自分だけで</strong>プログラムを考えてみよう。<br>
          「次のフェーズへ進む」を押すと、AIと話し合えるようになるよ。
        </div>
      </section>

      <!-- ③ AI 対話（フェーズ2以降） -->
      <section v-if="currentPhaseData.showChat" class="panel panel-chat">
        <h2 class="panel-title">{{ chatPanelTitle }}</h2>
        <p class="panel-desc">{{ chatPanelDesc }}</p>

        <div v-if="isGroupPhase" class="group-discussion-panel">
          <div class="group-panel-title">討論に参加する3つのAIグループ</div>
          <p class="group-panel-desc">
            各グループは下の案から考え始め、ほかの発言を聞いて考え直すこともあります。
          </p>
          <div class="group-example-list">
            <div
              v-for="example in GROUP_DISCUSSION_EXAMPLES"
              :key="example.group"
              class="group-example-card"
            >
              <div class="group-example-header">
                <span class="group-badge">{{ example.group }}</span>
                <strong>{{ example.title }}</strong>
              </div>
              <div class="group-rule-list">
                <div
                  v-for="ruleText in example.rules"
                  :key="ruleText"
                  class="group-rule-line"
                >
                  {{ ruleText }}
                </div>
              </div>
              <div class="group-question">{{ example.question }}</div>
            </div>
          </div>
        </div>

        <div class="chat-window" ref="chatWindowRef">
          <div
            v-for="msg in chatMessages"
            :key="msg.id"
            class="chat-bubble"
            :class="[
              msg.role === 'ai' ? 'bubble-ai' : (msg.role === 'group' ? 'bubble-group' : 'bubble-user'),
              msg.agentId ? `bubble-${msg.agentId}` : '',
            ]"
          >
            <div class="bubble-avatar">{{ messageSpeaker(msg) }}</div>
            <div class="bubble-text">{{ msg.text }}</div>
          </div>

          <div v-if="isLoading" class="chat-bubble bubble-ai loading-bubble">
            <div class="bubble-avatar">{{ isGroupPhase ? '司会AI' : 'AI' }}</div>
            <div class="bubble-text">
              {{ isGroupPhase ? 'A・B・Cグループで話し合い中' : '考え中' }}<span class="dots">...</span>
            </div>
          </div>

          <div ref="chatEndRef" />
        </div>

        <div class="chat-input-area">
          <textarea
            v-model="userInput"
            class="chat-input"
            :placeholder="chatInputPlaceholder"
            rows="2"
            :disabled="isLoading"
            @keydown="handleKeydown"
          />
          <button class="btn-send" :disabled="isLoading || !userInput.trim()" @click="sendMessage">
            送信
          </button>
        </div>

        <button class="btn-advice" :disabled="isLoading" @click="requestAdvice">
          {{ isLoading ? '考え中...' : adviceButtonLabel }}
        </button>
      </section>
    </main>
  </div>
</template>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

:root {
  --clr-bg: #f0f4f8;
  --clr-surface: #ffffff;
  --clr-primary: #3b6ff0;
  --clr-primary-light: #e8eeff;
  --clr-primary-dark: #2a54c8;
  --clr-success: #10b981;
  --clr-danger: #ef4444;
  --clr-warn: #f59e0b;
  --clr-text: #1e293b;
  --clr-muted: #64748b;
  --clr-border: #e2e8f0;
  --radius: 12px;
  --shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

body {
  font-family: 'Noto Sans JP', 'Hiragino Sans', sans-serif;
  background: var(--clr-bg);
  color: var(--clr-text);
  line-height: 1.6;
}

.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}


/* ── Phase Bar ── */
.phase-bar {
  background: white;
  border-bottom: 1px solid var(--clr-border);
  padding: 14px 24px;
}
.phase-bar-inner {
  max-width: 1400px;
  margin: 0 auto;
}
.phase-steps {
  display: flex;
  align-items: center;
  gap: 0;
  margin-bottom: 10px;
  flex-wrap: wrap;
  gap: 4px;
}
.phase-step {
  display: flex;
  align-items: center;
  gap: 6px;
  position: relative;
}
.step-circle {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.78rem;
  font-weight: 700;
  flex-shrink: 0;
  border: 2px solid var(--clr-border);
  background: white;
  color: var(--clr-muted);
  transition: all 0.2s;
}
.step-done .step-circle {
  background: var(--clr-success);
  border-color: var(--clr-success);
  color: white;
}
.step-active .step-circle {
  background: var(--clr-primary);
  border-color: var(--clr-primary);
  color: white;
  box-shadow: 0 0 0 3px rgba(59,111,240,0.2);
}
.step-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--clr-muted);
  white-space: nowrap;
}
.step-active .step-label { color: var(--clr-primary); }
.step-done .step-label { color: var(--clr-success); }
.step-future .step-label { color: var(--clr-muted); opacity: 0.6; }
.step-connector {
  width: 28px;
  height: 2px;
  background: var(--clr-border);
  margin: 0 6px;
  flex-shrink: 0;
}
.phase-desc {
  font-size: 0.83rem;
  color: var(--clr-text);
  background: var(--clr-primary-light);
  border-left: 3px solid var(--clr-primary);
  padding: 6px 12px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 10px;
}
.phase-nav { display: flex; align-items: center; }
.btn-next-phase {
  padding: 7px 18px;
  background: var(--clr-primary);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.84rem;
  font-family: inherit;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s, transform 0.1s;
}
.btn-next-phase:hover { background: var(--clr-primary-dark); transform: translateY(-1px); }
.btn-complete { background: var(--clr-success); }
.btn-complete:hover { background: #059669; transform: translateY(-1px); }

/* ── Problem Banner ── */
.problem-banner {
  background: #fefce8;
  border-bottom: 2px solid #fde68a;
  padding: 10px 24px;
  border-top: none;
}
.problem-inner {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.problem-label {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  background: #f59e0b;
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}
.problem-text { font-size: 0.88rem; color: #78350f; }

/* ── Main Grid ── */
.main-grid {
  display: grid;
  grid-template-columns: 2fr 1.5fr 1.5fr;
  gap: 20px;
  padding: 20px 24px 32px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  flex: 1;
  align-items: start;
}
@media (max-width: 1100px) {
  .main-grid { grid-template-columns: 1fr 1fr; }
  .panel-chat { grid-column: 1 / -1; }
}
@media (max-width: 700px) {
  .main-grid { grid-template-columns: 1fr; }
}

/* ── Panel ── */
.panel {
  background: var(--clr-surface);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow);
  border: 1px solid var(--clr-border);
}
.panel-title {
  font-size: 1.05rem;
  font-weight: 700;
  margin-bottom: 4px;
}
.panel-desc {
  font-size: 0.82rem;
  color: var(--clr-muted);
  margin-bottom: 16px;
  line-height: 1.5;
}

/* ── Panel title row ── */
.panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.panel-title-row .panel-title { margin-bottom: 0; }

.rule-aware-badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 20px;
  background: #d1fae5;
  color: #065f46;
  border: 1px solid #6ee7b7;
  white-space: nowrap;
  transition: background 0.3s;
}
.rule-aware-badge.badge-loading {
  background: #fef3c7;
  color: #92400e;
  border-color: #fcd34d;
  animation: pulse-badge 1s infinite;
}
@keyframes pulse-badge {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* ── Rules ── */
.rules-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
  min-height: 60px;
}
.empty-hint {
  color: var(--clr-muted);
  font-size: 0.84rem;
  padding: 20px;
  text-align: center;
  background: var(--clr-bg);
  border-radius: 8px;
  border: 2px dashed var(--clr-border);
}
.rule-card {
  background: var(--clr-primary-light);
  border: 1px solid #c7d7fb;
  border-radius: 10px;
  padding: 12px;
}
.rule-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  gap: 6px;
}
.rule-number { font-size: 0.75rem; font-weight: 700; color: var(--clr-primary); flex: 1; }
.rule-order-btns { display: flex; gap: 4px; }
.btn-order {
  width: 22px; height: 22px;
  border-radius: 4px;
  border: 1px solid var(--clr-border);
  background: white;
  color: var(--clr-muted);
  font-size: 0.7rem;
  cursor: pointer;
  transition: background 0.1s;
}
.btn-order:hover:not(:disabled) { background: var(--clr-primary-light); color: var(--clr-primary); }
.btn-order:disabled { opacity: 0.3; cursor: not-allowed; }
.btn-remove {
  width: 22px; height: 22px;
  border-radius: 50%;
  border: none;
  background: #fecaca;
  color: var(--clr-danger);
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-remove:hover { background: #fca5a5; }

.rule-body {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
}

.block-label { font-size: 0.7rem; color: var(--clr-muted); font-weight: 600; margin-bottom: 5px; display: block; }

.cond-group { display: flex; flex-direction: column; }
.cond-buttons { display: flex; flex-direction: column; gap: 5px; }
.cond-toggle {
  padding: 5px 10px;
  border-radius: 7px;
  border: 2px solid var(--clr-border);
  background: white;
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  color: var(--clr-muted);
  text-align: left;
  transition: all 0.15s;
}
.cond-toggle.active {
  border-color: var(--clr-primary);
  background: var(--clr-primary-light);
  color: var(--clr-primary);
  font-weight: 700;
}

.and-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
}
.and-badge {
  display: inline-block;
  padding: 2px 7px;
  background: var(--clr-primary);
  color: white;
  border-radius: 5px;
  font-size: 0.7rem;
  font-weight: 700;
}
.and-hint-text { font-size: 0.7rem; color: var(--clr-muted); }

.arrow-block {
  font-size: 1.4rem;
  color: var(--clr-primary);
  font-weight: 700;
  padding-top: 24px;
  flex-shrink: 0;
}

.action-group { display: flex; flex-direction: column; }
.action-buttons { display: flex; flex-direction: column; gap: 5px; }
.action-toggle {
  padding: 5px 12px;
  border-radius: 7px;
  border: 2px solid var(--clr-border);
  background: white;
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  color: var(--clr-muted);
  text-align: left;
  transition: all 0.15s;
}
.action-toggle.active {
  border-color: #f59e0b;
  background: #fffbeb;
  color: #92400e;
  font-weight: 700;
}

.rule-warn {
  margin-top: 8px;
  font-size: 0.75rem;
  color: var(--clr-warn);
  font-weight: 600;
}

.btn-add {
  width: 100%;
  padding: 10px;
  background: var(--clr-primary);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.88rem;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, transform 0.1s;
}
.btn-add:hover { background: var(--clr-primary-dark); transform: translateY(-1px); }

.ai-draft-box {
  margin-bottom: 12px;
  padding: 10px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  border-radius: 10px;
}
.ai-draft-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.ai-draft-title {
  font-size: 0.78rem;
  font-weight: 700;
  color: #1e40af;
}
.btn-apply-draft {
  border: none;
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 0.74rem;
  font-weight: 700;
  color: white;
  background: #2563eb;
  cursor: pointer;
}
.btn-apply-draft:hover { background: #1d4ed8; }
.ai-draft-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ai-draft-item {
  background: white;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  padding: 8px;
}
.ai-draft-number {
  display: inline-block;
  margin-bottom: 6px;
  font-size: 0.72rem;
  color: #1d4ed8;
  font-weight: 700;
}
.ai-draft-flow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.ai-draft-chip {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 0.75rem;
  background: #e0e7ff;
  color: #1e3a8a;
  font-weight: 600;
}
.ai-draft-chip.action {
  background: #ffedd5;
  color: #9a3412;
}
.ai-draft-arrow {
  font-size: 0.9rem;
  font-weight: 700;
  color: #334155;
}

/* ── Simulation ── */
.env-selector { margin-bottom: 16px; display: flex; flex-direction: column; gap: 10px; }
.env-row { display: flex; align-items: center; gap: 10px; }
.env-label { font-size: 0.78rem; font-weight: 600; color: var(--clr-muted); min-width: 60px; }
.env-buttons { display: flex; gap: 6px; }
.env-btn {
  padding: 5px 14px;
  border: 2px solid var(--clr-border);
  border-radius: 6px;
  background: white;
  font-size: 0.82rem;
  font-family: inherit;
  cursor: pointer;
  color: var(--clr-muted);
  transition: all 0.15s;
}
.env-btn.active {
  border-color: var(--clr-primary);
  background: var(--clr-primary-light);
  color: var(--clr-primary);
  font-weight: 700;
}

/* ── Visual Scene ── */
.sim-scene {
  position: relative;
  width: 100%;
  height: 220px;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 14px;
  transition: background 0.8s ease;
}
.scene-day {
  background: linear-gradient(to bottom, #87ceeb 0%, #c8e8f8 60%, #8db87a 60%, #7aaa60 100%);
}
.scene-night {
  background: linear-gradient(to bottom, #0b1340 0%, #1a2560 60%, #3a5230 60%, #2e4225 100%);
}

/* 空の装飾 */
.scene-sky { position: absolute; top: 0; left: 0; width: 100%; height: 60%; }
.sun {
  position: absolute;
  top: 14%;
  right: 12%;
  width: 32px;
  height: 32px;
  background: #ffd700;
  border-radius: 50%;
  box-shadow: 0 0 16px 4px rgba(255,220,0,0.5);
}
.star {
  position: absolute;
  width: 3px;
  height: 3px;
  background: white;
  border-radius: 50%;
  opacity: 0.9;
}

/* 地面 */
.scene-ground {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 40%;
}

/* 店舗 */
.store-building {
  position: absolute;
  bottom: 40%;
  left: 50%;
  transform: translateX(-50%);
  width: 160px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.store-sign-bar {
  width: 100%;
  background: #e74c3c;
  color: white;
  text-align: center;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.2em;
  padding: 4px 0;
  border-radius: 3px 3px 0 0;
}

/* チャイム */
.store-bell-wrap {
  position: absolute;
  top: -36px;
  right: 16px;
  display: flex;
  align-items: flex-end;
  gap: 4px;
}
.store-bell {
  display: flex;
  flex-direction: column;
  align-items: center;
  transform-origin: top center;
}
.bell-top {
  width: 6px;
  height: 6px;
  background: #888;
  border-radius: 50%;
}
.bell-body-shape {
  width: 18px;
  height: 16px;
  background: #e0a800;
  border-radius: 0 0 9px 9px;
  border: 2px solid #c08000;
}
.bell-clapper {
  width: 4px;
  height: 5px;
  background: #888;
  border-radius: 0 0 2px 2px;
}
@keyframes bell-ring {
  0%,100% { transform: rotate(0deg); }
  20%     { transform: rotate(-22deg); }
  50%     { transform: rotate(22deg); }
  80%     { transform: rotate(-14deg); }
}
.bell-ringing {
  animation: bell-ring 0.35s ease infinite;
}
.bell-wave {
  font-size: 0.9rem;
  color: #f59e0b;
  animation: wave-float 0.6s ease infinite alternate;
}
@keyframes wave-float {
  from { transform: translateY(0); opacity: 1; }
  to   { transform: translateY(-6px); opacity: 0.4; }
}

/* 自動ドア */
.door-frame {
  position: relative;
  width: 90px;
  height: 80px;
  background: #b0c8e0;
  border: 3px solid #7a9ab8;
  border-bottom: none;
  overflow: hidden;
}
.door-panel {
  position: absolute;
  top: 0;
  width: 50%;
  height: 100%;
  background: rgba(180, 220, 245, 0.7);
  border: 1px solid rgba(120, 180, 220, 0.8);
  transition: transform 0.5s ease;
}
.door-left  { left: 0;  transform: translateX(0); }
.door-right { right: 0; transform: translateX(0); }
.door-left.door-open  { transform: translateX(-100%); }
.door-right.door-open { transform: translateX(100%); }
.door-floor {
  position: absolute;
  bottom: -3px;
  left: -3px;
  right: -3px;
  height: 6px;
  background: #7a9ab8;
}

/* 人物 */
.person-figure {
  position: absolute;
  bottom: 40%;
  right: 16%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}
.person-head {
  width: 18px;
  height: 18px;
  background: #f5cba7;
  border-radius: 50%;
  border: 2px solid #d4a374;
}
.person-body {
  width: 20px;
  height: 26px;
  background: #3498db;
  border-radius: 3px;
}
.person-legs {
  display: flex;
  gap: 4px;
}
.leg {
  width: 8px;
  height: 18px;
  background: #2c3e50;
  border-radius: 0 0 3px 3px;
}
/* 人物の入退場アニメーション */
.person-slide-enter-active { transition: opacity 0.4s, transform 0.4s; }
.person-slide-leave-active { transition: opacity 0.3s, transform 0.3s; }
.person-slide-enter-from { opacity: 0; transform: translateX(40px); }
.person-slide-leave-to   { opacity: 0; transform: translateX(40px); }

.env-group-label { font-size: 0.78rem; font-weight: 600; color: var(--clr-muted); margin-bottom: 8px; }

.scenario-wrap { }
.scenario-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
  margin-bottom: 10px;
}
.scenario-table th {
  background: var(--clr-bg);
  padding: 6px 8px;
  text-align: center;
  font-weight: 700;
  color: var(--clr-muted);
  border-bottom: 2px solid var(--clr-border);
  font-size: 0.75rem;
}
.scenario-table td {
  padding: 6px 8px;
  text-align: center;
  border-bottom: 1px solid var(--clr-border);
  font-weight: 600;
}
.row-active { background: #eff6ff !important; }

/* ── Chat Placeholder (Phase 1) ── */
.panel-chat-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  min-height: 200px;
  background: var(--clr-bg);
  border: 2px dashed var(--clr-border);
  color: var(--clr-muted);
  gap: 10px;
}
.placeholder-title { font-size: 1rem; font-weight: 700; }
.placeholder-text { font-size: 0.82rem; line-height: 1.7; }

/* ── Chat ── */
.panel-chat { display: flex; flex-direction: column; }
.group-discussion-panel {
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid #c7d2fe;
  background: #eef2ff;
}
.group-panel-title {
  font-size: 0.86rem;
  font-weight: 800;
  color: #3730a3;
  margin-bottom: 4px;
}
.group-panel-desc {
  font-size: 0.78rem;
  color: #475569;
  margin-bottom: 10px;
  line-height: 1.5;
}
.group-example-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.group-example-card {
  background: white;
  border: 1px solid #ddd6fe;
  border-radius: 9px;
  padding: 9px;
}
.group-example-header {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 6px;
  font-size: 0.8rem;
}
.group-badge {
  padding: 2px 7px;
  border-radius: 999px;
  background: #4f46e5;
  color: white;
  font-size: 0.7rem;
  font-weight: 800;
  white-space: nowrap;
}
.group-rule-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 7px;
}
.group-rule-line {
  padding: 5px 7px;
  border-radius: 7px;
  background: #f8fafc;
  color: #334155;
  font-size: 0.74rem;
  font-weight: 700;
}
.group-question {
  padding: 6px 8px;
  border-left: 3px solid #6366f1;
  background: #eef2ff;
  color: #3730a3;
  font-size: 0.76rem;
  font-weight: 700;
  line-height: 1.5;
}
.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 300px;
  max-height: 420px;
  overflow-y: auto;
  padding: 4px 4px 12px;
  margin-bottom: 10px;
  border: 1px solid var(--clr-border);
  border-radius: 10px;
  background: var(--clr-bg);
}
.chat-bubble {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  max-width: 96%;
}
.bubble-ai { align-self: flex-start; }
.bubble-group { align-self: flex-start; }
.bubble-user { align-self: flex-end; flex-direction: row-reverse; }
.bubble-avatar {
  min-width: 58px;
  font-size: 0.72rem;
  font-weight: 700;
  text-align: center;
  flex-shrink: 0;
  margin-top: 8px;
}
.bubble-text {
  padding: 9px 13px;
  border-radius: 13px;
  font-size: 0.85rem;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble-ai .bubble-text {
  background: white;
  border: 1px solid var(--clr-border);
  border-top-left-radius: 4px;
}
.bubble-group .bubble-text {
  background: #f8fafc;
  border: 1px solid #cbd5e1;
  border-top-left-radius: 4px;
}
.bubble-group_a .bubble-text { border-left: 4px solid #f59e0b; }
.bubble-group_b .bubble-text { border-left: 4px solid #8b5cf6; }
.bubble-group_c .bubble-text { border-left: 4px solid #06b6d4; }
.bubble-user .bubble-text {
  background: var(--clr-primary);
  color: white;
  border-top-right-radius: 4px;
}

.dots { animation: blink 1.2s infinite; }
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.2; }
}

.chat-input-area {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}
.chat-input {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid var(--clr-border);
  border-radius: 8px;
  font-size: 0.84rem;
  font-family: inherit;
  resize: none;
  line-height: 1.5;
}
.chat-input:focus {
  outline: none;
  border-color: var(--clr-primary);
  box-shadow: 0 0 0 3px rgba(59,111,240,0.15);
}
.btn-send {
  padding: 0 16px;
  background: var(--clr-primary);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.84rem;
  font-family: inherit;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s;
  align-self: stretch;
}
.btn-send:hover:not(:disabled) { background: var(--clr-primary-dark); }
.btn-send:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-advice {
  width: 100%;
  padding: 11px;
  background: linear-gradient(135deg, #10b981, #059669);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.88rem;
  font-family: inherit;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
}
.btn-advice:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }
.btn-advice:disabled { opacity: 0.6; cursor: not-allowed; }

/* ── Settings FAB ── */
.settings-fab {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 200;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--clr-muted);
  color: white;
  border: none;
  font-size: 1.3rem;
  cursor: pointer;
  box-shadow: 0 3px 12px rgba(0,0,0,0.2);
  transition: background 0.15s, transform 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
}
.settings-fab:hover { background: var(--clr-text); transform: rotate(30deg); }

/* ── Settings Drawer ── */
.settings-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.45);
  z-index: 300;
  display: flex;
  justify-content: flex-end;
}
.settings-drawer {
  width: min(640px, 100vw);
  height: 100%;
  background: white;
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 24px rgba(0,0,0,0.15);
}
.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid var(--clr-border);
  flex-shrink: 0;
}
.settings-title {
  font-size: 1rem;
  font-weight: 700;
}
.settings-close {
  width: 32px; height: 32px;
  border-radius: 50%;
  border: none;
  background: var(--clr-bg);
  font-size: 1.1rem;
  cursor: pointer;
  color: var(--clr-muted);
}
.settings-close:hover { background: var(--clr-border); }

.settings-tabs {
  display: flex;
  gap: 8px;
  padding: 12px 24px 0;
  border-bottom: 1px solid var(--clr-border);
}
.settings-tab {
  padding: 9px 14px;
  border: 1px solid var(--clr-border);
  border-bottom: none;
  border-radius: 8px 8px 0 0;
  background: var(--clr-bg);
  color: var(--clr-muted);
  font-size: 0.82rem;
  font-family: inherit;
  font-weight: 700;
  cursor: pointer;
}
.settings-tab.active {
  background: white;
  color: var(--clr-primary);
  border-color: var(--clr-primary);
}

.settings-note {
  padding: 10px 24px;
  font-size: 0.78rem;
  color: var(--clr-muted);
  background: var(--clr-bg);
  border-bottom: 1px solid var(--clr-border);
  flex-shrink: 0;
}

.settings-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.prompt-block { display: flex; flex-direction: column; gap: 6px; }
.prompt-label {
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--clr-primary);
  letter-spacing: 0.02em;
}
.prompt-textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--clr-border);
  border-radius: 8px;
  font-family: 'Courier New', monospace;
  font-size: 0.78rem;
  line-height: 1.6;
  resize: vertical;
  color: var(--clr-text);
  background: #fafafa;
}
.prompt-textarea:focus {
  outline: none;
  border-color: var(--clr-primary);
  box-shadow: 0 0 0 3px rgba(59,111,240,0.12);
  background: white;
}

.dashboard-body { gap: 16px; }
.dashboard-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.dashboard-error {
  padding: 10px 12px;
  border-radius: 8px;
  background: #fef2f2;
  color: #991b1b;
  font-size: 0.82rem;
  font-weight: 700;
}
.dashboard-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.dashboard-card {
  padding: 14px;
  border: 1px solid var(--clr-border);
  border-radius: 10px;
  background: var(--clr-bg);
}
.dashboard-card-label {
  display: block;
  margin-bottom: 4px;
  font-size: 0.74rem;
  color: var(--clr-muted);
  font-weight: 700;
}
.dashboard-card strong {
  font-size: 1.35rem;
  color: var(--clr-text);
}
.dashboard-empty {
  padding: 18px;
  text-align: center;
  border: 2px dashed var(--clr-border);
  border-radius: 10px;
  color: var(--clr-muted);
  font-size: 0.84rem;
}
.dashboard-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--clr-border);
  border-radius: 10px;
}
.dashboard-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.78rem;
  min-width: 620px;
}
.dashboard-table th {
  background: var(--clr-bg);
  color: var(--clr-muted);
  font-weight: 800;
  text-align: left;
  padding: 9px 10px;
  border-bottom: 1px solid var(--clr-border);
  white-space: nowrap;
}
.dashboard-table td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--clr-border);
  white-space: nowrap;
}
.dashboard-table tr:last-child td { border-bottom: none; }
.dash-ok {
  color: #047857;
  font-weight: 800;
}
.dash-ng {
  color: #b45309;
  font-weight: 800;
}

.settings-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 24px;
  border-top: 1px solid var(--clr-border);
  flex-shrink: 0;
}
.settings-msg {
  flex: 1;
  font-size: 0.82rem;
  color: var(--clr-success);
  font-weight: 600;
}
.btn-reset-prompt {
  padding: 8px 16px;
  border: 1px solid var(--clr-border);
  border-radius: 7px;
  background: white;
  font-size: 0.82rem;
  font-family: inherit;
  cursor: pointer;
  color: var(--clr-muted);
}
.btn-reset-prompt:hover:not(:disabled) { background: var(--clr-bg); }
.btn-reset-prompt:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-save-prompt {
  padding: 8px 20px;
  background: var(--clr-primary);
  color: white;
  border: none;
  border-radius: 7px;
  font-size: 0.82rem;
  font-family: inherit;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-save-prompt:hover:not(:disabled) { background: var(--clr-primary-dark); }
.btn-save-prompt:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Drawer transition ── */
.drawer-enter-active { transition: opacity 0.2s; }
.drawer-leave-active { transition: opacity 0.2s; }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-active .settings-drawer { transition: transform 0.25s ease; }
.drawer-leave-active .settings-drawer { transition: transform 0.2s ease; }
.drawer-enter-from .settings-drawer { transform: translateX(100%); }
.drawer-leave-to .settings-drawer { transform: translateX(100%); }
</style>
