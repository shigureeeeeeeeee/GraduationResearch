<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import PhaseBar from './PhaseBar.vue'
import ChatPanel from './ChatPanel.vue'
import SettingsDrawer from './SettingsDrawer.vue'
import VentilationProgram from './VentilationProgram.vue'
import VentilationSimulation from './VentilationSimulation.vue'
import VentilationBrief from './VentilationBrief.vue'
import VentilationCompare from './VentilationCompare.vue'
import VentilationBoard from './VentilationBoard.vue'
import { compareSummaries, programSummary } from '../ruleText'
import * as api from '../services/ventilationApi'
import '../ventilation.css'

const STORAGE_KEY = 'ventilation-lab-goals-v3'
const clone = (value) => JSON.parse(JSON.stringify(value))
function readDraft() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') } catch { return null }
}
const saved = readDraft()
const phases = [
  { id: 1, label: '1人で考える', desc: '目的と装置の制限から、自分の条件と優先方針を考えよう。シミュレーションで動かして確かめられます。' },
  { id: 2, label: 'ペアで対話する', desc: 'ペア（AI）も自分の案を持っています。2つの案の違いについて、お互いの理由を話そう。' },
  { id: 3, label: '実行して確認する', desc: 'いろいろなテストケースを動かして、気になった場面をペアと話そう。' },
  { id: 4, label: '全体で対話する', desc: '4つの案を比べて一番よい案を選び、1案ずつみんなで話し合ってから、選び直そう。' },
]
// ペア（AI）はA案かC案を持つ。B案は全テストケースで達成するので、ペアに持たせると答えを渡すことになる
const PAIR_PLANS = ['group_a', 'group_c']
const GROUP_PLANS = ['group_a', 'group_b', 'group_c']
const newBoard = () => ({ step: 'choose', before: null, after: null, focus: null, discussed: [] })
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
// 全テストケースの結果。プログラムを変えると古くなるので保存せず、変更時に消す
const allCases = ref(null)
const baseline = ref(saved?.baseline || null)
const messages = ref(saved?.messages || [])
const pairPlan = ref(saved?.pairPlan || null)
const board = ref(saved?.board || newBoard())
// グループの案のカード（プログラムと全テストケースの結果）。サーバーから取り直せるので保存しない
const plans = ref({})
const learnerResults = ref(null)
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
    predictions: predictions.value,
    pair_plan: phase.value === 2 || phase.value === 3 ? pairPlan.value : null,
    focus_plan: phase.value === 4 ? board.value.focus : null })
}
function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ sessionId: sessionId.value, phase: phase.value, program: program.value,
      steps: steps.value, predictions: predictions.value, scenarioId: scenarioId.value, environment: environment.value,
      messages: messages.value, completed: completed.value, pendingLogs: pendingLogs.value, baseline: baseline.value,
      pairPlan: pairPlan.value, board: board.value }))
    localError.value = ''
  } catch { localError.value = 'ブラウザへの一時保存ができません。画面を閉じる前にログ保存状況を確認してください。' }
}
watch([sessionId, phase, program, steps, predictions, scenarioId, environment, messages, completed, pendingLogs, baseline, pairPlan, board], persist, { deep: true })

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
  const selected = config.value.scenarios.find((item) => item.id === scenarioId.value)
  if (selected) environment.value = clone(selected.steps[0])
}
function updateProgram(next) {
  if (locked.value) return
  if (steps.value.length) {
    void saveLog('program_revision', { next_program: next })
    baseline.value = clone({ program: program.value, steps: steps.value })
    notice.value = '変更前の実行を記録し、初期状態に戻しました。'
    clearRun()
  }
  allCases.value = null
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
  if (locked.value) return
  simBusy.value = true
  errorMessage.value = ''
  notice.value = ''
  const nextSteps = [...clone(steps.value), clone(environment.value)]
  try {
    const response = await api.simulate(program.value, nextSteps, baseline.value)
    steps.value = nextSteps
    result.value = response
    await saveLog('step')
    const selected = config.value.scenarios.find((item) => item.id === scenarioId.value)
    if (selected?.steps[steps.value.length]) environment.value = clone(selected.steps[steps.value.length])
  } catch (error) { errorMessage.value = `実行できませんでした。${error.message}` }
  finally { simBusy.value = false }
}
async function runAllCases() {
  if (locked.value) return
  simBusy.value = true
  errorMessage.value = ''
  notice.value = ''
  try {
    allCases.value = await api.simulateAll(program.value)
    await saveLog('run_all', { scenario_id: 'all' })
  } catch (error) { errorMessage.value = `まとめて実行できませんでした。${error.message}` }
  finally { simBusy.value = false }
}
function openCase(id) {
  resetRun(id)
  notice.value = `${config.value.scenarios.find((item) => item.id === id)?.label} を1分ずつ確かめます。`
}
async function ensurePlans(ids) {
  const missing = ids.filter((id) => !plans.value[id])
  if (!missing.length) return
  for (const card of await api.fetchPlans(missing)) plans.value[card.id] = card
}
async function refreshLearnerResults() {
  try { learnerResults.value = await api.simulateAll(program.value) } catch { learnerResults.value = null }
}
// フェーズの最初の発言。ペアは自分の案との違いを話題にし、司会役は進め方だけを伝える
function introFor(nextPhase) {
  if (nextPhase === 2) {
    const pair = plans.value[pairPlan.value]
    const first = compareSummaries(programSummary(config.value, program.value), programSummary(config.value, pair.program)).find((stage) => !stage.same)
    const text = !Object.values(program.value).flat().length
      ? 'ぼくも自分で作ってみたよ。まだルールがないみたいだけど、どこから考えてる？'
      : first ? `ぼくも自分で作ってみたよ。並べてみたら${first.name}のところが違うね。そこはどうしてそうしたの？` : 'ぼくも作ってみたら、同じ案になったよ。どうしてそうしたの？'
    return { role: 'ai', speaker: 'ペア', agentId: 'pair', text }
  }
  if (nextPhase === 3) return { role: 'ai', speaker: 'ペア', agentId: 'pair', text: 'いろいろ動かしてみようよ。気になったテストケースってある？' }
  return { role: 'ai', speaker: '司会役', agentId: 'facilitator', text: 'ここからはみんなで話そう。まず上に並んだ4つの案から、一番いいと思う案を選んで理由を書いてみて。' }
}
async function advance() {
  if (locked.value || phase.value >= 4) return
  phaseBusy.value = true
  errorMessage.value = ''
  try {
    const nextPhase = phase.value + 1
    if (nextPhase === 2) {
      pairPlan.value = pairPlan.value || PAIR_PLANS[Math.floor(Math.random() * PAIR_PLANS.length)]
      await ensurePlans([pairPlan.value])
    }
    if (nextPhase === 4) {
      await ensurePlans(GROUP_PLANS)
      await refreshLearnerResults()
    }
    await saveLog('phase_complete')
    phase.value = nextPhase
    messages.value.push({ id: crypto.randomUUID(), phase: nextPhase, ...introFor(nextPhase) })
  } catch (error) { errorMessage.value = `次のフェーズの準備ができませんでした。${error.message}` }
  finally { phaseBusy.value = false }
}
// 研究者用：任意のフェーズへ移動する（開発・予備実験の確認用）。学習者の画面には出さず、移動はログに残す
async function jumpToPhase(target) {
  if (busy.value || target === phase.value) return
  phaseBusy.value = true
  errorMessage.value = ''
  try {
    if (target === 2 || target === 3) {
      pairPlan.value = pairPlan.value || PAIR_PLANS[Math.floor(Math.random() * PAIR_PLANS.length)]
      await ensurePlans([pairPlan.value])
    }
    if (target === 4) { await ensurePlans(GROUP_PLANS); await refreshLearnerResults() }
    phase.value = target
    completed.value = false
    // ログには移動先のフェーズが入る。移動元は直前の記録のフェーズで分かる
    await saveLog('phase_jump')
    notice.value = `フェーズ${target}に移動しました（実験者設定から）。`
  } catch (error) { errorMessage.value = `フェーズを移動できませんでした。${error.message}` }
  finally { phaseBusy.value = false }
}
async function choosePlan(choice) {
  if (locked.value) return
  board.value = { ...board.value, [choice.stage]: choice, step: choice.stage === 'before' ? 'discuss' : 'try' }
  await saveLog('choice', { choice })
}
async function discussPlan(planId) {
  if (locked.value) return
  board.value = { ...board.value, focus: planId }
  // 話し合いが最後まで届いたときだけ「話した」にする
  if (await talk(true)) board.value = { ...board.value, discussed: [...new Set([...board.value.discussed, planId])] }
}
function finishDiscussion() {
  board.value = { ...board.value, step: 'rechoose', focus: null }
}
async function complete() {
  if (locked.value) return
  phaseBusy.value = true
  const stored = await saveLog('session_end')
  if (stored) { completed.value = true; notice.value = '実行履歴と対話を保存しました。'; errorMessage.value = '' }
  phaseBusy.value = false
}
async function talk(isAdvice = false) {
  const text = isAdvice ? null : userInput.value.trim()
  if (locked.value || (!isAdvice && !text)) return false
  let ok = false
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
      if (data.facts) messages.value.push({ id: crypto.randomUUID(), role: 'system', speaker: '実行結果', phase: talkingPhase, text: data.facts })
      messages.value.push({ id: crypto.randomUUID(), role: 'ai', speaker: 'ペア', agentId: 'pair', phase: talkingPhase, text: data.message, llm: data.llm })
    }
    ok = true
  } catch (error) {
    errorMessage.value = error.name === 'AbortError' ? '対話の受信を中断しました。' : 'AI対話に接続できませんでした。バックエンドを確認してください。'
  } finally {
    await saveLog('chat')
    chatBusy.value = false
    chatAbort = null
    await chatPanel.value?.scrollToBottom()
  }
  return ok
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
  allCases.value = null
  pairPlan.value = null
  board.value = newBoard()
  learnerResults.value = null
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
    if (!Number.isInteger(phase.value) || phase.value < 1 || phase.value > 4) throw new Error('保存されたセッションの形式を確認できません。')
    // 実行前の予想は廃止した。以前のブラウザ保存に残る予想は、以降の記録と数が合わなくなるため破棄する
    predictions.value = []
    result.value = await api.simulate(program.value, steps.value, baseline.value)
    // 再読み込みしたときは、そのフェーズで使う案を取り直す
    if (phase.value === 2 || phase.value === 3) {
      // この変更より前の保存から再開したときは、ペアの案がまだ決まっていない
      pairPlan.value = pairPlan.value || PAIR_PLANS[Math.floor(Math.random() * PAIR_PLANS.length)]
      await ensurePlans([pairPlan.value])
    }
    if (phase.value === 4) { await ensurePlans(GROUP_PLANS); await refreshLearnerResults() }
    ready.value = true
    if (pendingLogs.value.length) void flushLogs()
  } catch (error) { startupError.value = `課題を読み込めませんでした。バックエンドの起動を確認してください。${error.message}` }
}
// フェーズ4では、自分の案のカードの結果をプログラムの変更に合わせて更新する
let resultsTimer = null
watch(program, () => {
  if (phase.value !== 4) return
  clearTimeout(resultsTimer)
  resultsTimer = setTimeout(refreshLearnerResults, 400)
}, { deep: true })
onMounted(initialize)
onBeforeUnmount(() => chatAbort?.abort())
</script>

<template>
  <div class="app ventilation-app">
    <SettingsDrawer>
      <template #session>
        <button type="button" class="env-btn" :disabled="busy" @click="newSession">新しいセッションを始める</button>
        <label class="phase-jump">フェーズを移動
          <select :value="phase" :disabled="busy" @change="jumpToPhase(Number($event.target.value))">
            <option v-for="item in phases" :key="item.id" :value="item.id">{{ item.id }}. {{ item.label }}</option>
          </select>
        </label>
        <span class="lab-muted small">{{ pendingLogs.length ? `ログ送信待ち ${pendingLogs.length} 件` : '次の参加者の前に押してください。現在の記録はログに保存します。' }}</span>
      </template>
    </SettingsDrawer>
    <div class="problem-banner">
      <div class="problem-inner">
        <VentilationBrief v-if="ready" :config="config" />
        <template v-else><span class="problem-label">課題</span><span class="problem-text">自習室A・Bで1台の換気装置を共有する制御を考えます。</span></template>
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
      <div v-if="phase === 4" class="board-wrap">
        <VentilationBoard :config="config" :program="program" :plans="GROUP_PLANS.map((id) => plans[id]).filter(Boolean)" :learner-results="learnerResults" :board="board" :disabled="locked" @choose="choosePlan" @discuss="discussPlan" @finish-discussion="finishDiscussion" />
      </div>
      <main class="main-grid lab-workspace" :class="{ 'no-chat': phase === 1 }">
        <VentilationProgram :model-value="program" :config="config" :latest="result.trace.at(-1) || null" :disabled="locked" @update:model-value="updateProgram" />
        <VentilationSimulation :config="config" :environment="environment" :result="result" :program="program" :scenario-id="scenarioId" :all-cases="allCases" :disabled="locked" @environment="updateEnvironment" @scenario="resetRun" @reset="resetRun()" @step="runStep" @run-all="runAllCases" @open-case="openCase" />
        <div class="lab-chat" :class="{ 'panel-chat': phase > 1 }">
          <VentilationCompare v-if="phase === 2 || phase === 3" :config="config" :program="program" :pair="plans[pairPlan] || null" />
          <ChatPanel ref="chatPanel" v-model="userInput" :visible="phase > 1" :group-phase="groupPhase" :title="groupPhase ? '全体での話し合い' : 'ペアとの対話'" :description="groupPhase ? 'A・B・Cグループと司会役もAIの仲間です。話す案は上の一覧から選びます。実行結果はシステムが示します。' : 'ペア（AI）はあなたと同じ課題に取り組んでいる仲間で、正解を知っているわけではありません。'" input-placeholder="考えた理由や、気になった場面を話してみよう" :advice-label="groupPhase ? 'この案についてもう少し話す' : 'ペアに話しかけてもらう'" :messages="messages" :loading="chatBusy" :disabled="locked || (groupPhase && !board.focus && board.step !== 'try')" :group-examples="[]" @send="talk()" @request-advice="talk(true)" />
          <button v-if="chatBusy" class="env-btn cancel-discussion" @click="chatAbort?.abort()">対話の受信を中断</button>
        </div>
      </main>
    </template>
  </div>
</template>
