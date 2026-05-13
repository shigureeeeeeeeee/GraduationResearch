<script setup>
import { ref, computed, nextTick } from 'vue'

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
    desc: 'AIがクラスの他のグループのプログラムを紹介してくれるよ。それについて意見を言ってみよう。',
    showChat: true,
  },
]

const currentPhase = ref(1)
const currentPhaseData = computed(() => PHASES[currentPhase.value - 1])

const PHASE_INTRO_MESSAGES = {
  2: 'こんにちは！ペアの対話フェーズだね。\nあなたのプログラム、どんなルールにした？私のと比べてみたいな。教えてくれる？',
  3: '実行して確認するフェーズだよ！\n4つの場面（昼・人あり、昼・人なし、夜・人あり、夜・人なし）を全部チェックしてみよう。全部✓になるかな？',
  4: 'みんなのプログラムが出揃ったところで、全体で話し合おう！\n他のグループが作ったプログラムを紹介するね。まず「今のプログラムについてアドバイスをもらう」ボタンを押してみて。',
}

function advancePhase() {
  if (currentPhase.value >= 4) return
  const next = currentPhase.value + 1
  currentPhase.value = next
  if (PHASE_INTRO_MESSAGES[next]) {
    chatMessages.value.push({
      id: Date.now(),
      role: 'ai',
      text: PHASE_INTRO_MESSAGES[next],
    })
    nextTick(() => chatEndRef.value?.scrollIntoView({ behavior: 'smooth' }))
  }
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

async function sendMessage() {
  const text = userInput.value.trim()
  if (!text || isLoading.value) return

  chatMessages.value.push({ id: Date.now(), role: 'user', text })
  userInput.value = ''
  await scrollToBottom()

  isLoading.value = true
  try {
    const r = simResult.value
    const res = await fetch('http://localhost:8001/api/advice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rules: rulesForApi.value,
        environment: env.value,
        result: { ...r, allCorrect: allCorrect.value },
        history: chatMessages.value
          .filter((m) => m.id !== 0)
          .map((m) => ({ role: m.role, text: m.text })),
        phase: currentPhase.value,
      }),
    })
    const data = await res.json()
    chatMessages.value.push({ id: Date.now() + 1, role: 'ai', text: data.message })
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
    const r = simResult.value
    const res = await fetch('http://localhost:8001/api/advice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rules: rulesForApi.value,
        environment: env.value,
        result: { ...r, allCorrect: allCorrect.value },
        history: chatMessages.value
          .filter((m) => m.id !== 0)
          .map((m) => ({ role: m.role, text: m.text })),
        phase: currentPhase.value,
      }),
    })
    const data = await res.json()
    chatMessages.value.push({ id: Date.now(), role: 'ai', text: data.message })
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
</script>

<template>
  <div class="app">
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
          <span v-else class="phase-final-msg">全フェーズ完了</span>
        </div>
      </div>
    </div>

    <main class="main-grid" :class="{ 'no-chat': !currentPhaseData.showChat }">
      <!-- ① プログラム構築 -->
      <section class="panel panel-builder">
        <h2 class="panel-title">プログラム構築</h2>
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
        <h2 class="panel-title">AI との対話</h2>
        <p class="panel-desc">
          考えたことや疑問をAIに話しかけてみよう。<br>
          ヒントをもらいながら一緒に考えられます。
        </p>

        <div class="chat-window" ref="chatWindowRef">
          <div
            v-for="msg in chatMessages"
            :key="msg.id"
            class="chat-bubble"
            :class="msg.role === 'ai' ? 'bubble-ai' : 'bubble-user'"
          >
            <div class="bubble-avatar">{{ msg.role === 'ai' ? 'AI' : 'あなた' }}</div>
            <div class="bubble-text">{{ msg.text }}</div>
          </div>

          <div v-if="isLoading" class="chat-bubble bubble-ai loading-bubble">
            <div class="bubble-avatar">AI</div>
            <div class="bubble-text">考え中<span class="dots">...</span></div>
          </div>

          <div ref="chatEndRef" />
        </div>

        <div class="chat-input-area">
          <textarea
            v-model="userInput"
            class="chat-input"
            placeholder="AIに話しかける（Enterで送信、Shift+Enterで改行）"
            rows="2"
            :disabled="isLoading"
            @keydown="handleKeydown"
          />
          <button class="btn-send" :disabled="isLoading || !userInput.trim()" @click="sendMessage">
            送信
          </button>
        </div>

        <button class="btn-advice" :disabled="isLoading" @click="requestAdvice">
          {{ isLoading ? '考え中...' : '今のプログラムについてアドバイスをもらう' }}
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
.phase-final-msg { font-size: 0.88rem; font-weight: 700; color: var(--clr-success); }

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
.bubble-user { align-self: flex-end; flex-direction: row-reverse; }
.bubble-avatar { font-size: 1.1rem; flex-shrink: 0; margin-top: 2px; }
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
</style>
