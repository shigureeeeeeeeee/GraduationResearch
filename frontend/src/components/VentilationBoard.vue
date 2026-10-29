<script setup>
import { computed, ref, watch } from 'vue'
import { programSummary } from '../ruleText'

// フェーズ4：4つの案を並べ、選ぶ → 1案ずつ話す → 選び直す → 取り込んで試す（中山ら2019の考察②③）
const props = defineProps({
  config: { type: Object, required: true },
  program: { type: Object, required: true },
  plans: { type: Array, required: true },
  learnerResults: { type: Object, default: null },
  board: { type: Object, required: true },
  disabled: Boolean,
})
const emit = defineEmits(['choose', 'discuss', 'finish-discussion'])
const STEPS = [
  { id: 'choose', label: '一番よい案を選ぶ' },
  { id: 'discuss', label: '1案ずつ話し合う' },
  { id: 'rechoose', label: 'もう一度選ぶ' },
  { id: 'try', label: '自分の案に取り込んで試す' },
]
const selected = ref('')
const reason = ref('')
watch(() => props.board.step, () => { selected.value = ''; reason.value = '' })

const cards = computed(() => [
  ...props.plans.map((plan) => ({ id: plan.id, name: `${plan.group}の案`, title: plan.title, program: plan.program, results: plan.results })),
  { id: 'learner', name: 'あなたの案', title: '今のプログラム', program: props.program, results: props.learnerResults },
].map((card) => ({ ...card, stages: programSummary(props.config, card.program),
  met: card.results?.cases.filter((item) => item.goals_met).length,
  urgent: card.results?.cases.reduce((sum, item) => sum + item.urgent_unserved, 0) })))
const choosing = computed(() => ['choose', 'rechoose'].includes(props.board.step))
const stepIndex = computed(() => STEPS.findIndex((item) => item.id === props.board.step))
const nameOf = (id) => cards.value.find((card) => card.id === id)?.name

function submitChoice() {
  if (!selected.value || !reason.value.trim()) return
  emit('choose', { stage: props.board.step === 'choose' ? 'before' : 'after', plan: selected.value, reason: reason.value.trim() })
}
</script>

<template>
  <section class="plan-board">
    <ol class="board-steps">
      <li v-for="(item, index) in STEPS" :key="item.id" :class="{ done: index < stepIndex, current: index === stepIndex }">{{ index + 1 }}. {{ item.label }}</li>
    </ol>
    <p class="board-instruction">
      <template v-if="board.step === 'choose'">4つの案を見比べて、この自習室に一番合うと思う案を1つ選び、理由を書こう。</template>
      <template v-else-if="board.step === 'discuss'">話し合う案を選んで「この案について話す」を押そう。どの案から話してもいいし、何度話してもいい。話し終えたら、もう一度選び直そう。</template>
      <template v-else-if="board.step === 'rechoose'">話し合いを踏まえて、もう一度一番よいと思う案を選び、理由を書こう。最初と同じ案でもいい。</template>
      <template v-else>選んだ案の考えを自分のプログラムに取り込み、「全テストケースをまとめて実行」で確かめよう。終わったら上の「完了」を押してね。</template>
    </p>
    <div class="board-cards">
      <article v-for="card in cards" :key="card.id" class="plan-card"
        :class="{ focus: board.focus === card.id, chosen: selected === card.id, learner: card.id === 'learner' }">
        <header>
          <label v-if="choosing" class="plan-select"><input v-model="selected" type="radio" name="plan-choice" :value="card.id" :disabled="disabled"><strong>{{ card.name }}</strong></label>
          <strong v-else>{{ card.name }}</strong>
          <span class="plan-title">{{ card.title }}</span>
          <span v-if="board.discussed.includes(card.id)" class="discussed-chip">話した</span>
        </header>
        <div class="plan-results" :title="card.results ? '' : '結果を計算中'">
          <template v-if="card.results">
            <span v-for="item in card.results.cases" :key="item.id" class="result-cell" :class="item.goals_met ? 'met' : 'unmet'" :title="item.label">{{ item.goals_met ? '✓' : '✗' }}</span>
            <small>{{ card.met }} / {{ card.results.cases.length }} 個で達成・1,500ppm以上の放置 合計{{ card.urgent }}分</small>
          </template>
          <small v-else>結果を計算しています…</small>
        </div>
        <details class="plan-rules">
          <summary>ルールを見る</summary>
          <section v-for="stage in card.stages" :key="stage.id">
            <h5>{{ stage.name }}</h5>
            <ol><li v-for="(text, i) in stage.rules" :key="i">{{ text }}</li><li v-if="!stage.rules.length" class="empty">ルールなし</li></ol>
          </section>
        </details>
        <button v-if="board.step === 'discuss'" type="button" class="env-btn discuss-button" :disabled="disabled" @click="emit('discuss', card.id)">この案について話す</button>
      </article>
    </div>
    <p class="lab-muted small">✓ / ✗ は8つのテストケース（1〜8）で3つの目的を達成できたか。カーソルを合わせるとテストケース名が出ます。</p>
    <div v-if="choosing" class="board-choice">
      <label>選んだ理由
        <textarea v-model="reason" rows="2" maxlength="2000" :disabled="disabled" placeholder="どの場面を考えて、その案がよいと思ったか" />
      </label>
      <button type="button" class="btn-next-phase" :disabled="disabled || !selected || !reason.trim()" @click="submitChoice">{{ selected ? `${nameOf(selected)}に決めた` : '案を選んでね' }}</button>
    </div>
    <div v-else-if="board.step === 'discuss'" class="board-choice">
      <button type="button" class="env-btn" :disabled="disabled || !board.discussed.length" @click="emit('finish-discussion')">話し合いを終えて、もう一度選ぶ</button>
    </div>
    <p v-if="board.before" class="lab-muted small">最初に選んだ案：{{ nameOf(board.before.plan) }}（{{ board.before.reason }}）<template v-if="board.after"> ／ 選び直した案：{{ nameOf(board.after.plan) }}（{{ board.after.reason }}）</template></p>
  </section>
</template>
