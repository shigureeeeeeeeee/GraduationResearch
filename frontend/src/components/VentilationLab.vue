<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import PhaseBar from './PhaseBar.vue'
import ChatPanel from './ChatPanel.vue'
import SettingsDrawer from './SettingsDrawer.vue'
import VentilationProgram from './VentilationProgram.vue'
import VentilationSimulation from './VentilationSimulation.vue'
import * as api from '../services/ventilationApi'
import '../ventilation.css'

const STORAGE_KEY = 'ventilation-lab-goals-v3'
const clone = (value) => JSON.parse(JSON.stringify(value))
function readDraft() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') } catch { return null }
}
const saved = readDraft()
const phases = [
  { id: 1, label: '1人で考える', desc: '目的と装置の制限から、自分の条件と優先方針を考えよう。実行前に、次の動作を予想してください。' },
  { id: 2, label: 'ペアで対話する', desc: 'AIに自分の判断の理由を伝え、見落としている場面がないか一緒に考えよう。' },
  { id: 3, label: '実行して確認する', desc: '経過を1ステップずつ進め、動作と内部状態を確かめよう。修正理由も記録してください。' },
  { id: 4, label: '全体で対話する', desc: 'A・B・Cグループの案と実行結果を比べ、自分のプログラムを見直そう。' },
]
const intros = {
  2: 'ペアの対話を始めよう。今のプログラムを読んで、一緒に検討します。特に迷った条件や、その順番にした理由を聞かせてくれる？',
  3: '次は経過を変えて確かめよう。同じ濃度でも、前の状態や待ち時間が違うとどう動くと予想する？',
  4: 'A・B・Cの案には、それぞれ異なる判断の仕方があります。討論を進めると、各案の実行結果を比べられます。',
}
const initialState = () => ({ demand: { A: false, B: false }, wait: { A: 0, B: 0 }, output: 'stop', run: 0 })
const emptyResult = () => ({ trace: [], state: initialState(), metrics: {}, constraints_met: false })
const config = ref(null)
const ready = ref(false)
const startupError = ref('')
const sessionId = ref(saved?.sessionId || crypto.randomUUID())
const phase = ref(saved?.phase || 1)
const program = ref(saved?.program || { demand: [], selection: [], output: [] })
const steps = ref(saved?.steps || [])
const predictions = ref(saved?.predictions || [])
const scenarioId = ref(saved?.scenarioId || 'shared')
const environment = ref(saved?.environment || { aOccupied: true, bOccupied: true, aCo2: 1200, bCo2: 1100, maintenance: false })
const result = ref(emptyResult())
const baseline = ref(saved?.baseline || null)
const prediction = ref('')
const predictionReason = ref('')
const reflection = ref(saved?.reflection || '')
const messages = ref(saved?.messages || [])
const userInput = ref('')
const chatPanel = ref(null)
const completed = ref(saved?.completed || false)
const pendingLogs = ref(saved?.pendingLogs || [])
const logError = ref('')
const localError = ref('')
const errorMessage = ref('')
const notice = ref('')
const simBusy = ref(false)
const chatBusy = ref(false)
const phaseBusy = ref(false)
const busy = computed(() => simBusy.value || chatBusy.value || phaseBusy.value)
const locked = computed(() => busy.value || completed.value)
const groupPhase = computed(() => phase.value === 4)
let chatAbort = null
let flushPromise = null

function history(phase4Only = false) {
  return messages.value.filter((message) => !phase4Only || message.phase === 4).slice(-200)
    .map(({ role, text, speaker, phase, llm }) => ({ role, text, speaker, phase, ...(llm ? { llm } : {}) }))
}
function payload(currentMessage = null) {
  return clone({ task_id: 'ventilation-goals-v3', program: program.value, steps: steps.value, baseline: baseline.value, environment: environment.value,
    history: history(groupPhase.value), current_message: currentMessage, phase: phase.value,
    reflection: reflection.value, predictions: predictions.value })
}
function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ sessionId: sessionId.value, phase: phase.value, program: program.value,
      steps: steps.value, predictions: predictions.value, scenarioId: scenarioId.value, environment: environment.value,
      reflection: reflection.value, messages: messages.value, completed: completed.value, pendingLogs: pendingLogs.value, baseline: baseline.value }))
    localError.value = ''
  } catch { localError.value = 'ブラウザへの一時保存ができません。画面を閉じる前にログ保存状況を確認してください。' }
}
watch([sessionId, phase, program, steps, predictions, scenarioId, environment, reflection, messages, completed, pendingLogs, baseline], persist, { deep: true })

function flushLogs() {
  if (flushPromise) return flushPromise
  flushPromise = (async () => {
    logError.value = ''
    while (pendingLogs.value.length) {
      try {
        await api.saveSessionLog(pendingLogs.value[0])
        pendingLogs.value.shift()
      } catch {
        logError.value = 'ログを送信できませんでした。記録はこのブラウザに保持されています。'
        return false
      }
    }
    return true
  })().finally(() => { flushPromise = null })
  return flushPromise
}
function saveLog(event, extra = {}) {
  pendingLogs.value.push({ ...payload(), history: history(), session_id: sessionId.value, event_id: crypto.randomUUID(),
    event, scenario_id: scenarioId.value, predictions: clone(predictions.value), ...clone(extra) })
  persist()
  return flushLogs()
}
function clearRun() {
  steps.value = []
  predictions.value = []
  result.value = emptyResult()
  prediction.value = ''
  predictionReason.value = ''
  const selected = config.value.scenarios.find((item) => item.id === scenarioId.value)
  if (selected) environment.value = clone(selected.steps[0])
}
function updateProgram(next) {
  if (locked.value) return
  if (steps.value.length) {
    void saveLog('program_revision', { next_program: next })
    baseline.value = clone({ program: program.value, steps: steps.value })
    notice.value = '変更前の実行と修正理由を記録し、初期状態に戻しました。'
    clearRun()
    reflection.value = ''
  }
  program.value = next
}
function resetRun(nextScenario = scenarioId.value) {
  if (locked.value) return
  if (steps.value.length) void saveLog('reset')
  scenarioId.value = nextScenario
  clearRun()
  errorMessage.value = ''
  notice.value = '初期状態から検証を始めます。'
}
function updateEnvironment(next) {
  environment.value = next
  scenarioId.value = 'custom'
}
async function runStep() {
  if (locked.value || !prediction.value) return
  simBusy.value = true
  errorMessage.value = ''
  notice.value = ''
  const nextSteps = [...clone(steps.value), clone(environment.value)]
  try {
    const response = await api.simulate(program.value, nextSteps, baseline.value)
    steps.value = nextSteps
    predictions.value.push({ output: prediction.value, reason: predictionReason.value })
    result.value = response
    await saveLog('step')
    prediction.value = ''
    predictionReason.value = ''
    const selected = config.value.scenarios.find((item) => item.id === scenarioId.value)
    if (selected?.steps[steps.value.length]) environment.value = clone(selected.steps[steps.value.length])
  } catch (error) { errorMessage.value = `実行できませんでした。${error.message}` }
  finally { simBusy.value = false }
}
async function advance() {
  if (locked.value || phase.value >= 4) return
  phaseBusy.value = true
  await saveLog('phase_complete')
  phase.value += 1
  messages.value.push({ id: crypto.randomUUID(), role: 'ai', speaker: phase.value === 4 ? '司会AI' : 'AI', phase: phase.value, text: intros[phase.value] })
  phaseBusy.value = false
}
async function complete() {
  if (locked.value) return
  if (!reflection.value.trim()) {
    errorMessage.value = '最後に「気づき・修正理由」を記入してから保存してください。'
    document.getElementById('reflection')?.focus()
    return
  }
  phaseBusy.value = true
  const stored = await saveLog('session_end')
  if (stored) { completed.value = true; notice.value = '実行履歴・対話・振り返りを保存しました。'; errorMessage.value = '' }
  phaseBusy.value = false
}
async function talk(isAdvice = false) {
  const text = isAdvice ? null : userInput.value.trim()
  if (locked.value || (!isAdvice && !text)) return
  const request = payload(text)
  const talkingPhase = phase.value
  if (text) {
    messages.value.push({ id: crypto.randomUUID(), role: 'user', speaker: 'あなた', phase: talkingPhase, text })
    userInput.value = ''
  }
  chatBusy.value = true
  chatAbort = new AbortController()
  errorMessage.value = ''
  try {
    if (talkingPhase === 4) {
      await api.streamGroupDiscussion(request, async (turn) => {
        messages.value.push({ id: crypto.randomUUID(), role: turn.role, speaker: turn.speaker,
          agentId: turn.agent_id, phase: talkingPhase, text: turn.text, llm: turn.llm })
        await chatPanel.value?.scrollToBottom()
      }, chatAbort.signal)
    } else {
      const data = await api.fetchAdvice(request, chatAbort.signal)
      messages.value.push({ id: crypto.randomUUID(), role: 'ai', speaker: 'AI', phase: talkingPhase, text: data.message, llm: data.llm })
    }
  } catch (error) {
    errorMessage.value = error.name === 'AbortError' ? '対話の受信を中断しました。' : 'AI対話に接続できませんでした。バックエンドを確認してください。'
  } finally {
    await saveLog('chat')
    chatBusy.value = false
    chatAbort = null
    await chatPanel.value?.scrollToBottom()
  }
}
async function newSession() {
  if (busy.value) return
  if (ready.value && !confirm('新しいセッションを始めますか？現在の記録はログに保存します。')) return
  phaseBusy.value = true
  if (ready.value && !completed.value) await saveLog('reset')
  sessionId.value = crypto.randomUUID()
  baseline.value = null
  phase.value = 1
  program.value = { demand: [], selection: [], output: [] }
  scenarioId.value = 'shared'
  messages.value = []
  reflection.value = ''
  completed.value = false
  clearRun()
  startupError.value = ''
  errorMessage.value = ''
  ready.value = true
  notice.value = '新しいセッションを始めました。'
  phaseBusy.value = false
}
async function initialize() {
  startupError.value = ''
  try {
    config.value = await api.fetchConfig()
    if (!Number.isInteger(phase.value) || phase.value < 1 || phase.value > 4 || predictions.value.length !== steps.value.length) throw new Error('保存されたセッションの形式を確認できません。')
    result.value = await api.simulate(program.value, steps.value, baseline.value)
    ready.value = true
    if (pendingLogs.value.length) void flushLogs()
  } catch (error) { startupError.value = `課題を読み込めませんでした。バックエンドの起動を確認してください。${error.message}` }
}
onMounted(initialize)
onBeforeUnmount(() => chatAbort?.abort())
</script>

<template>
  <div class="app ventilation-app">
    <SettingsDrawer task="ventilation" />
    <div class="problem-banner">
      <div class="problem-inner">
        <span class="problem-label">課題</span>
        <span class="problem-text">自習室A・Bで<strong>1台の換気装置</strong>を共有しています。<strong>連続未対応4ステップ以内・無人や800ppm以下への運転0回・装置の制約違反0回</strong>を達成する条件と優先方針を考えましょう。</span>
        <details v-if="ready" class="task-instructions"><summary>目的・装置の制限・使える情報</summary>
          <p>換気を始める・終える条件、どちらの部屋を優先するかを自分で決め、その理由を説明してください。</p>
          <template v-for="section in [{ title: '数値で確認する達成基準', items: config.goals }, { title: '達成後の改善目標', items: [config.improvement] }, { title: '装置の制限', items: config.constraints }, { title: '情報と検討の目安', items: config.guidance }]" :key="section.title">
            <p><strong>{{ section.title }}</strong></p>
            <ol><li v-for="item in section.items" :key="item.title"><strong>{{ item.title }}</strong>：{{ item.text }}</li></ol>
          </template>
          <p>条件を追加して比較する値を選び、必要ならAND・OR・NOTを使います。条件なしはいつでも一致。各段階は上から最初に一致したルールを使うので、優先順位を考えて並べてください。装置の制約も自分のルールで表現します。</p>
          <p>要求 → 候補 → 命令の順に決め、最後にカウンターを更新します。「前回の要求」「待ち時間」「前回の動作」はステップ開始時の値です。CO₂濃度は入力値で、換気による変化の物理計算はしません。</p>
        </details>
      </div>
    </div>
    <div v-if="!ready" class="lab-loading" role="status">
      <p>{{ startupError || '課題を読み込んでいます…' }}</p>
      <button v-if="startupError" class="btn-next-phase" @click="initialize">再読み込み</button>
      <button v-if="startupError && config" class="env-btn" @click="newSession">初期状態から始める</button>
    </div>
    <template v-else>
      <PhaseBar :phases="phases" :current-phase="phase" :current-phase-data="phases[phase - 1]" :disabled="busy || completed" :completed="completed" @advance="advance" @complete="complete" />
      <div v-if="errorMessage || notice || logError || localError" class="lab-messages">
        <div v-if="errorMessage" class="lab-error" role="alert">{{ errorMessage }}</div>
        <div v-if="notice" class="lab-notice" role="status">{{ notice }}</div>
        <div v-if="logError || localError" class="lab-error" role="alert">{{ logError }} {{ localError }}<button v-if="pendingLogs.length" class="text-button" @click="flushLogs">未送信 {{ pendingLogs.length }} 件を再送</button></div>
      </div>
      <main class="main-grid lab-workspace" :class="{ 'no-chat': phase === 1 }">
        <VentilationProgram :model-value="program" :config="config" :disabled="locked" @update:model-value="updateProgram" />
        <VentilationSimulation :config="config" :environment="environment" :result="result" :program="program" :scenario-id="scenarioId" :predictions="predictions" :prediction="prediction" :prediction-reason="predictionReason" :disabled="locked" @environment="updateEnvironment" @scenario="resetRun" @reset="resetRun()" @step="runStep" @prediction="prediction = $event" @prediction-reason="predictionReason = $event">
          <div class="reflection-fields">
            <label for="reflection" class="env-group-label">気づき・修正理由</label>
            <textarea id="reflection" v-model="reflection" :disabled="locked" maxlength="10000" rows="3" placeholder="予想と違った点、変更したい条件、その理由を残そう。" aria-label="気づきと修正理由" />
            <button class="env-btn" :disabled="locked || !reflection.trim()" @click="saveLog('reflection').then((ok) => { if (ok) notice = '気づき・修正理由を保存しました。' })">この記述を保存</button>
            <p class="lab-muted small">{{ pendingLogs.length ? `ログ送信待ち ${pendingLogs.length} 件` : '変更はブラウザに一時保存されます' }}</p>
            <button type="button" class="text-button session-reset" :disabled="busy" @click="newSession">新しいセッション</button>
          </div>
        </VentilationSimulation>
        <div class="lab-chat" :class="{ 'panel-chat': phase > 1 }">
          <ChatPanel ref="chatPanel" v-model="userInput" :visible="phase > 1" :group-phase="groupPhase" :title="groupPhase ? '全体対話' : 'AI との対話'" :description="groupPhase ? '各グループが重視した目的と、実行結果をもとに話し合います。' : '今のプログラムと実行履歴をAIが読み、判断の理由を問いかけます。'" input-placeholder="考えた理由や、確かめたい場面を伝えてみよう" :advice-label="groupPhase ? 'A・B・Cグループの討論を進める' : '今のプログラムについて話し合う'" :messages="messages" :loading="chatBusy" :disabled="locked" :group-examples="config.groups" group-description="濃度への対応、待ち時間、運転の継続を重視する案を比較します。" @send="talk()" @request-advice="talk(true)" />
          <button v-if="chatBusy" class="env-btn cancel-discussion" @click="chatAbort?.abort()">対話の受信を中断</button>
        </div>
      </main>
    </template>
  </div>
</template>
