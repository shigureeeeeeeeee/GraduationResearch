<script setup>
import { ref, computed } from 'vue'

// ─────────────────────────────────────────────
// 定数
// ─────────────────────────────────────────────
const CONDITION_OPTIONS = [
  { value: '', label: '-- 条件を選ぶ --' },
  { value: 'div3', label: '3の倍数（N % 3 == 0）' },
  { value: 'div5', label: '5の倍数（N % 5 == 0）' },
  { value: 'always', label: '常に（else）' },
]

const ACTION_OPTIONS = [
  { value: '', label: '-- 出力を選ぶ --' },
  { value: 'fizz', label: '"Fizz" を出力' },
  { value: 'buzz', label: '"Buzz" を出力' },
  { value: 'fizzbuzz', label: '"FizzBuzz" を出力' },
  { value: 'number', label: 'N をそのまま出力' },
]

const PRESET_NUMBERS = [1, 3, 5, 9, 15, 30]

// ─────────────────────────────────────────────
// プログラム構築
// ─────────────────────────────────────────────
const rules = ref([])

function addRule() {
  rules.value.push({
    id: Date.now().toString(),
    cond1: '',
    cond2: '',
    action: '',
  })
}

function removeRule(id) {
  rules.value = rules.value.filter((r) => r.id !== id)
}

function moveUp(index) {
  if (index === 0) return
  const arr = rules.value
  ;[arr[index - 1], arr[index]] = [arr[index], arr[index - 1]]
  rules.value = [...arr]
}

function moveDown(index) {
  if (index === rules.value.length - 1) return
  const arr = rules.value
  ;[arr[index], arr[index + 1]] = [arr[index + 1], arr[index]]
  rules.value = [...arr]
}

// API 送信用フォーマットに変換
const rulesForApi = computed(() =>
  rules.value
    .filter((r) => r.action)
    .map((r) => ({
      id: r.id,
      conditions: [
        ...(r.cond1 ? [{ type: r.cond1 }] : []),
        ...(r.cond2 ? [{ type: r.cond2 }] : []),
      ],
      action: r.action,
    }))
)

// ─────────────────────────────────────────────
// シミュレーション
// ─────────────────────────────────────────────
const inputN = ref(15)

// 正解のFizzBuzz出力
function correctOutput(n) {
  if (n % 3 === 0 && n % 5 === 0) return 'FizzBuzz'
  if (n % 3 === 0) return 'Fizz'
  if (n % 5 === 0) return 'Buzz'
  return String(n)
}

const ACTION_LABEL = {
  fizz: 'Fizz',
  buzz: 'Buzz',
  fizzbuzz: 'FizzBuzz',
  number: String(inputN.value),
}

// ルールを上から評価し最初に一致したアクションを返す（if-elif-else 方式）
const simResult = computed(() => {
  const n = inputN.value
  const conds = {
    div3: n % 3 === 0,
    div5: n % 5 === 0,
    always: true,
  }

  for (const rule of rulesForApi.value) {
    const allMet =
      rule.conditions.length === 0
        ? false
        : rule.conditions.every((c) => conds[c.type] ?? false)

    if (allMet) {
      const output =
        rule.action === 'number'
          ? String(n)
          : { fizz: 'Fizz', buzz: 'Buzz', fizzbuzz: 'FizzBuzz' }[rule.action] ?? '?'
      const expected = correctOutput(n)
      return { output, expected, is_correct: output === expected }
    }
  }

  const expected = correctOutput(n)
  return { output: '(なし)', expected, is_correct: false }
})

// 全プリセットケースのサマリ
const allCases = computed(() =>
  PRESET_NUMBERS.map((n) => {
    const conds = { div3: n % 3 === 0, div5: n % 5 === 0, always: true }
    let output = '(なし)'
    for (const rule of rulesForApi.value) {
      const allMet =
        rule.conditions.length > 0 &&
        rule.conditions.every((c) => conds[c.type] ?? false)
      if (allMet) {
        output =
          rule.action === 'number'
            ? String(n)
            : { fizz: 'Fizz', buzz: 'Buzz', fizzbuzz: 'FizzBuzz' }[rule.action] ?? '?'
        break
      }
    }
    const expected = correctOutput(n)
    return { n, output, expected, ok: output === expected }
  })
)

// ─────────────────────────────────────────────
// AI チャット
// ─────────────────────────────────────────────
/* const chatMessages = ref([
  {
    id: 0,
    role: 'ai',
    text: 'こんにちは！FizzBuzz のルールをブロックで作ってみよう。できたら「AIにアドバイスをもらう」ボタンを押してね。',
  },
])
 */
const isLoading = ref(false)

async function getAdvice() {
  if (isLoading.value) return

  const r = simResult.value
  chatMessages.value.push({
    id: Date.now(),
    role: 'user',
    text: `N = ${inputN.value} のテスト結果を確認してください。\n出力: ${r.output} ／ 期待値: ${r.expected} ／ ${r.is_correct ? '✓ 正解' : '✗ 不正解'}`,
  })

  isLoading.value = true
  try {
    const res = await fetch('http://localhost:8001/api/advice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rules: rulesForApi.value,
        environment: { n: inputN.value },
        result: r,
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
  }
}
</script>

<template>
  <div class="app">
    <header class="header">
      <div class="header-inner">
        <div class="header-tag">競技プログラミング 入門問題</div>
        <h1>FizzBuzz チャレンジ</h1>
        <p class="subtitle">
          ブロックを並べてFizzBuzzのルールを完成させよう！ルールは<strong>上から順に</strong>評価されます。
        </p>
      </div>
    </header>

    <!-- 問題文バナー -->
    <div class="problem-banner">
      <div class="problem-inner">
        <span class="problem-label">問題</span>
        <span class="problem-text">
          整数 N が与えられたとき → 3の倍数かつ5の倍数なら <code>FizzBuzz</code>、
          3の倍数なら <code>Fizz</code>、5の倍数なら <code>Buzz</code>、
          それ以外は <code>N</code> をそのまま出力せよ。
        </span>
      </div>
    </div>

    <main class="main-grid">
      <!-- ① プログラム構築エリア -->
      <section class="panel panel-builder">
        <h2 class="panel-title">プログラム構築</h2>
        <p class="panel-desc">
          条件とアクションを選んでルールを作ろう。ルールは<strong>上から順</strong>に評価されるぞ。
        </p>

        <div class="rules-list">
          <div
            v-for="(rule, index) in rules"
            :key="rule.id"
            class="rule-card"
          >
            <div class="rule-header">
              <span class="rule-number">ルール {{ index + 1 }}</span>
              <div class="rule-order-btns">
                <button class="btn-order" :disabled="index === 0" @click="moveUp(index)" title="上へ">▲</button>
                <button class="btn-order" :disabled="index === rules.length - 1" @click="moveDown(index)" title="下へ">▼</button>
              </div>
              <button class="btn-remove" @click="removeRule(rule.id)" title="削除">×</button>
            </div>

            <div class="rule-body">
              <!-- 条件 1 -->
              <div class="block condition-block">
                <label class="block-label">条件①</label>
                <select v-model="rule.cond1" class="select">
                  <option
                    v-for="opt in CONDITION_OPTIONS"
                    :key="opt.value"
                    :value="opt.value"
                  >{{ opt.label }}</option>
                </select>
              </div>

              <!-- AND + 条件 2 -->
              <template v-if="rule.cond1 && rule.cond1 !== 'always'">
                <div class="block and-block">
                  <span class="and-badge">AND</span>
                </div>
                <div class="block condition-block">
                  <label class="block-label">条件②（任意）</label>
                  <select v-model="rule.cond2" class="select">
                    <option value="">-- なし --</option>
                    <option
                      v-for="opt in CONDITION_OPTIONS.slice(1, 3)"
                      :key="opt.value"
                      :value="opt.value"
                      :disabled="opt.value === rule.cond1"
                    >{{ opt.label }}</option>
                  </select>
                </div>
              </template>

              <!-- Arrow -->
              <div class="arrow-block">→</div>

              <!-- アクション -->
              <div class="block action-block">
                <label class="block-label">出力</label>
                <select v-model="rule.action" class="select select-action">
                  <option
                    v-for="opt in ACTION_OPTIONS"
                    :key="opt.value"
                    :value="opt.value"
                  >{{ opt.label }}</option>
                </select>
              </div>
            </div>
          </div>

          <div v-if="rules.length === 0" class="empty-hint">
            まだルールがありません。「＋ ルールを追加」から作り始めよう！
          </div>
        </div>

        <button class="btn-add" @click="addRule">＋ ルールを追加</button>
      </section>

      <!-- ② シミュレーションエリア -->
      <section class="panel panel-sim">
        <h2 class="panel-title">シミュレーション</h2>
        <p class="panel-desc">N を選んで、プログラムの出力を確認しよう。</p>

        <!-- N 選択 -->
        <div class="n-selector">
          <p class="env-group-label">テストする N を選ぶ</p>
          <div class="preset-row">
            <button
              v-for="num in PRESET_NUMBERS"
              :key="num"
              class="preset-btn"
              :class="{ active: inputN === num }"
              @click="inputN = num"
            >
              {{ num }}
            </button>
          </div>
          <div class="custom-n-row">
            <label class="block-label">または直接入力</label>
            <input
              type="number"
              v-model.number="inputN"
              min="1"
              max="999"
              class="n-input"
            />
          </div>
        </div>

        <!-- 現在のN の結果 -->
        <div class="current-result">
          <div class="result-n-label">N = <strong>{{ inputN }}</strong> のとき</div>
          <div class="result-row">
            <div class="result-box">
              <div class="result-box-label">あなたの出力</div>
              <div class="result-box-value" :class="simResult.is_correct ? 'val-correct' : 'val-wrong'">
                {{ simResult.output }}
              </div>
            </div>
            <div class="result-sep">vs</div>
            <div class="result-box">
              <div class="result-box-label">正解</div>
              <div class="result-box-value val-expected">{{ simResult.expected }}</div>
            </div>
          </div>
          <div class="result-badge" :class="simResult.is_correct ? 'badge-ok' : 'badge-ng'">
            {{ simResult.is_correct ? '✓ 正解！' : '✗ 不正解' }}
          </div>
        </div>

        <!-- 全ケースの表 -->
        <div class="case-table-wrap">
          <p class="env-group-label" style="margin-bottom: 6px;">主要テストケース一覧</p>
          <table class="case-table">
            <thead>
              <tr>
                <th>N</th>
                <th>3倍数</th>
                <th>5倍数</th>
                <th>出力</th>
                <th>正解</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="c in allCases"
                :key="c.n"
                :class="{ 'row-active': c.n === inputN }"
                @click="inputN = c.n"
                style="cursor: pointer;"
              >
                <td><strong>{{ c.n }}</strong></td>
                <td>{{ c.n % 3 === 0 ? '✓' : '—' }}</td>
                <td>{{ c.n % 5 === 0 ? '✓' : '—' }}</td>
                <td :class="c.ok ? 'td-ok' : 'td-ng'">{{ c.output }}</td>
                <td class="td-expected">{{ c.expected }}</td>
                <td>{{ c.ok ? '✓' : '✗' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- ③ AI 対話エリア -->
      <section class="panel panel-chat">
        <h2 class="panel-title">AIアドバイス</h2>
        <p class="panel-desc">AIが問いかけで考えるヒントをくれます。</p>

        <div class="chat-window">
          <div
            v-for="msg in chatMessages"
            :key="msg.id"
            class="chat-bubble"
            :class="msg.role === 'ai' ? 'bubble-ai' : 'bubble-user'"
          >
            <div class="bubble-text">{{ msg.text }}</div>
          </div>

          <div v-if="isLoading" class="chat-bubble bubble-ai loading-bubble">
            <div class="bubble-text">考え中<span class="dots">...</span></div>
          </div>
        </div>

        <button class="btn-advice" :disabled="isLoading" @click="getAdvice">
          {{ isLoading ? '考え中...' : 'AIにアドバイスをもらう' }}
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
  font-family: 'Noto Sans JP', sans-serif;
  background: var(--clr-bg);
  color: var(--clr-text);
  line-height: 1.6;
}

.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ── Header ── */
.header {
  background: linear-gradient(135deg, #1e3a8a 0%, #3b6ff0 100%);
  color: white;
  padding: 20px 24px;
}

.header-inner {
  max-width: 1400px;
  margin: 0 auto;
}

.header-tag {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  opacity: 0.75;
  margin-bottom: 4px;
}

.header h1 {
  font-size: 1.6rem;
  font-weight: 700;
}

.subtitle {
  margin-top: 4px;
  font-size: 0.88rem;
  opacity: 0.9;
}

/* ── Problem Banner ── */
.problem-banner {
  background: #fefce8;
  border-bottom: 2px solid #fde68a;
  padding: 10px 24px;
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
  text-transform: uppercase;
  background: #f59e0b;
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}

.problem-text {
  font-size: 0.88rem;
  color: #78350f;
}

.problem-text code {
  font-family: 'Courier New', monospace;
  background: #fde68a;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 700;
  font-size: 0.85em;
}

/* ── Main Grid ── */
.main-grid {
  display: grid;
  grid-template-columns: 2fr 1.4fr 1.4fr;
  gap: 20px;
  padding: 20px 24px 32px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  flex: 1;
  align-items: start;
}

@media (max-width: 1024px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
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
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.panel-desc {
  font-size: 0.82rem;
  color: var(--clr-muted);
  margin-bottom: 16px;
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
  padding: 10px 12px;
}

.rule-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  gap: 6px;
}

.rule-number {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--clr-primary);
  flex: 1;
}

.rule-order-btns {
  display: flex;
  gap: 4px;
}

.btn-order {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  border: 1px solid var(--clr-border);
  background: white;
  color: var(--clr-muted);
  font-size: 0.7rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.1s;
}

.btn-order:hover:not(:disabled) {
  background: var(--clr-primary-light);
  color: var(--clr-primary);
}

.btn-order:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-remove {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: none;
  background: #fecaca;
  color: var(--clr-danger);
  font-size: 0.9rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.btn-remove:hover { background: #fca5a5; }

.rule-body {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  flex-wrap: wrap;
}

.block { display: flex; flex-direction: column; gap: 3px; }
.block-label { font-size: 0.7rem; color: var(--clr-muted); font-weight: 500; }

.select {
  padding: 5px 8px;
  border: 1px solid var(--clr-border);
  border-radius: 7px;
  font-size: 0.8rem;
  font-family: inherit;
  background: white;
  color: var(--clr-text);
  cursor: pointer;
  min-width: 150px;
  transition: border-color 0.15s;
}

.select:focus {
  outline: none;
  border-color: var(--clr-primary);
  box-shadow: 0 0 0 3px rgba(59, 111, 240, 0.15);
}

.and-block { padding-bottom: 3px; }
.and-badge {
  display: inline-block;
  padding: 2px 7px;
  background: var(--clr-primary);
  color: white;
  border-radius: 5px;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.arrow-block {
  font-size: 1.3rem;
  color: var(--clr-primary);
  font-weight: 700;
  padding-bottom: 2px;
  flex-shrink: 0;
}

.select-action {
  background: #fffbeb;
  border-color: #fcd34d;
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

.btn-add:hover {
  background: var(--clr-primary-dark);
  transform: translateY(-1px);
}

/* ── Simulation ── */
.n-selector { margin-bottom: 18px; }
.env-group-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--clr-muted);
  margin-bottom: 8px;
}

.preset-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.preset-btn {
  padding: 5px 12px;
  border: 2px solid var(--clr-border);
  border-radius: 6px;
  background: white;
  font-size: 0.9rem;
  font-family: 'Courier New', monospace;
  font-weight: 700;
  cursor: pointer;
  color: var(--clr-muted);
  transition: all 0.15s;
}

.preset-btn.active {
  border-color: var(--clr-primary);
  background: var(--clr-primary-light);
  color: var(--clr-primary);
}

.preset-btn:hover:not(.active) { border-color: #94a3b8; color: var(--clr-text); }

.custom-n-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.n-input {
  width: 80px;
  padding: 5px 8px;
  border: 1px solid var(--clr-border);
  border-radius: 7px;
  font-size: 0.9rem;
  font-family: 'Courier New', monospace;
  font-weight: 700;
  text-align: center;
}

.n-input:focus {
  outline: none;
  border-color: var(--clr-primary);
}

/* current result */
.current-result {
  background: var(--clr-bg);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 16px;
  text-align: center;
}

.result-n-label {
  font-size: 0.82rem;
  color: var(--clr-muted);
  margin-bottom: 10px;
}

.result-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 10px;
}

.result-box {
  background: white;
  border: 1px solid var(--clr-border);
  border-radius: 8px;
  padding: 10px 16px;
  min-width: 90px;
}

.result-box-label {
  font-size: 0.7rem;
  color: var(--clr-muted);
  font-weight: 600;
  margin-bottom: 4px;
}

.result-box-value {
  font-size: 1.3rem;
  font-weight: 800;
  font-family: 'Courier New', monospace;
}

.val-correct { color: var(--clr-success); }
.val-wrong { color: var(--clr-danger); }
.val-expected { color: var(--clr-text); }

.result-sep { font-size: 0.82rem; color: var(--clr-muted); }

.result-badge {
  display: inline-block;
  padding: 3px 14px;
  border-radius: 20px;
  font-size: 0.82rem;
  font-weight: 700;
}

.badge-ok { background: #d1fae5; color: #065f46; }
.badge-ng { background: #fee2e2; color: #991b1b; }

/* case table */
.case-table-wrap { overflow-x: auto; }

.case-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}

.case-table th {
  background: var(--clr-bg);
  padding: 6px 8px;
  text-align: center;
  font-weight: 700;
  color: var(--clr-muted);
  border-bottom: 2px solid var(--clr-border);
  font-size: 0.75rem;
}

.case-table td {
  padding: 6px 8px;
  text-align: center;
  border-bottom: 1px solid var(--clr-border);
  font-family: 'Courier New', monospace;
  font-weight: 600;
}

.case-table .row-active { background: #eff6ff; }

.td-ok { color: var(--clr-success); }
.td-ng { color: var(--clr-danger); }
.td-expected { color: var(--clr-muted); }

/* ── Chat ── */
.panel-chat { display: flex; flex-direction: column; }

.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 280px;
  max-height: 460px;
  overflow-y: auto;
  padding: 2px 2px 12px;
  margin-bottom: 12px;
}

.chat-bubble {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  max-width: 94%;
}

.bubble-ai { align-self: flex-start; }
.bubble-user { align-self: flex-end; flex-direction: row-reverse; }

.bubble-text {
  padding: 9px 13px;
  border-radius: 13px;
  font-size: 0.85rem;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble-ai .bubble-text {
  background: var(--clr-primary-light);
  border: 1px solid #c7d7fb;
  border-top-left-radius: 4px;
}

.bubble-user .bubble-text {
  background: #1e293b;
  color: #e2e8f0;
  border-top-right-radius: 4px;
  font-size: 0.8rem;
}

.dots { animation: blink 1.2s infinite; }

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.2; }
}

.btn-advice {
  width: 100%;
  padding: 12px;
  background: linear-gradient(135deg, #10b981, #059669);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.92rem;
  font-family: inherit;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
}

.btn-advice:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }
.btn-advice:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
