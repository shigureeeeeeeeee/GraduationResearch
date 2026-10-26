<script setup>
import { computed, ref } from 'vue'
import VentilationVisual from './VentilationVisual.vue'
import VentilationTimeline from './VentilationTimeline.vue'

const props = defineProps({
  config: { type: Object, required: true },
  environment: { type: Object, required: true },
  result: { type: Object, required: true },
  program: { type: Object, required: true },
  scenarioId: { type: String, required: true },
  allCases: { type: Object, default: null },
  disabled: Boolean,
})
const emit = defineEmits(['environment', 'scenario', 'step', 'reset', 'run-all', 'open-case'])
const CHECK_COLUMNS = [{ id: 'wait', label: '放置', title: '連続の放置は4分以内' }, { id: 'unnecessary', label: 'ムダ', title: '無人・800ppm以下への運転0回' }, { id: 'constraints', label: '制限', title: '装置の制限違反0回' }]
// 一覧では「テストケース」を省いて番号と名前だけにする
const shortLabel = (label) => label.replace(/^テストケース(\d+)：/, '$1. ')
const metCount = computed(() => props.allCases?.cases.filter((item) => item.goals_met).length ?? 0)
const checkOf = (item, id) => item.checks.find((check) => check.id === id)
const OUTPUTS = [{ value: 'A', label: 'A室を換気' }, { value: 'B', label: 'B室を換気' }, { value: 'stop', label: '停止' }]
const outputLabel = (value) => OUTPUTS.find((item) => item.value === value)?.label
const scenario = computed(() => props.config.scenarios.find((item) => item.id === props.scenarioId))
const finished = computed(() => !!scenario.value && props.result.trace.length >= scenario.value.steps.length)
const latest = computed(() => props.result.trace.at(-1))
const goalWait = computed(() => latest.value?.observation.goal_wait || { A: 0, B: 0 })
const editingInput = ref(false)
const showInputEditor = computed(() => props.scenarioId === 'custom' || editingInput.value)

function environmentChange(key, value) {
  if (key.endsWith('Co2')) value = Number.isFinite(value) ? Math.min(10000, Math.max(0, Math.round(value))) : 0
  emit('environment', { ...props.environment, [key]: value })
}
</script>

<template>
  <section class="panel panel-simulation simulation-lab">
    <div class="panel-title-row">
      <h2 class="panel-title">シミュレーション</h2>
      <span class="lab-muted small">経過 {{ result.trace.length }}分{{ scenario ? ` / 全${scenario.steps.length}分` : '' }}</span>
    </div>
    <fieldset :disabled="disabled" class="program-fieldset">
      <section class="all-cases">
        <h3 class="env-group-label">全テストケースでまとめて確認</h3>
        <button type="button" class="btn-next-phase run-all-button" @click="emit('run-all')">全テストケースをまとめて実行</button>
        <template v-if="allCases">
          <p class="all-cases-summary" :class="allCases.all_met ? 'met' : 'unmet'">{{ allCases.all_met ? `${allCases.cases.length}個すべてで目的を達成しました` : `${allCases.cases.length}個中 ${metCount}個で達成。✗ のテストケースを1分ずつ見て、原因を探そう。` }}</p>
          <div class="table-scroll">
            <table class="scenario-table all-cases-table">
              <thead><tr><th>テストケース（押すと1分ずつ見られます）</th><th v-for="column in CHECK_COLUMNS" :key="column.id" :title="column.title">{{ column.label }}</th></tr></thead>
              <tbody>
                <tr v-for="item in allCases.cases" :key="item.id" :class="{ failed: !item.goals_met }">
                  <td><button type="button" class="case-link" @click="emit('open-case', item.id)">{{ shortLabel(item.label) }}</button><small>{{ item.minutes }}分間・1,500ppm以上の放置 {{ item.urgent_unserved }}分</small></td>
                  <td v-for="column in CHECK_COLUMNS" :key="column.id" class="check-cell" :class="checkOf(item, column.id).met ? 'met' : 'unmet'" :title="`実測 ${checkOf(item, column.id).actual}`">{{ checkOf(item, column.id).met ? '✓' : '✗' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="lab-muted small">放置＝連続の放置4分以内、ムダ＝無人・800ppm以下への運転0回、制限＝装置の制限違反0回。<br>改善目標：1,500ppm以上の部屋の放置は全テストケースで合計 {{ allCases.cases.reduce((sum, item) => sum + item.urgent_unserved, 0) }} 分。</p>
        </template>
        <p v-else class="lab-muted small">今のプログラムで8つのテストケースを最後まで実行し、目的を達成できたかを一覧にします。プログラムを変えたら、もう一度実行してください。</p>
      </section>
      <h3 class="env-group-label one-case-heading">1つずつ確かめる</h3>
      <div class="scenario-controls">
        <label>テストケース
          <select :value="scenarioId" aria-label="テストケース" @change="emit('scenario', $event.target.value)">
            <option v-for="item in config.scenarios" :key="item.id" :value="item.id">{{ item.label }}</option>
            <option value="custom">自分でテストケースを作る</option>
          </select>
        </label>
        <button type="button" class="env-btn" @click="emit('reset')">最初から</button>
      </div>
      <p class="lab-muted small">{{ scenario ? `${scenario.description}（${scenario.steps.length}分間。人の出入りと濃度はあらかじめ決まっています）` : '人の有無や濃度を1分ずつ自分で決めて、確かめたい場面を作れます。' }}</p>

      <VentilationVisual :environment="environment" :state="result.state" :goal-wait="goalWait" :next-step="result.trace.length + 1" :finished="finished" />

      <button v-if="scenarioId !== 'custom'" type="button" class="text-button" :aria-expanded="showInputEditor" @click="editingInput = !editingInput">{{ showInputEditor ? '入力の編集を閉じる' : '次の入力を自分で変える' }}</button>
      <div v-if="showInputEditor" class="input-editor">
        <p class="lab-muted small">変更すると「自分でテストケースを作る」に切り替わります。</p>
        <div class="input-editor-grid">
          <div v-for="room in ['A', 'B']" :key="room" class="input-room">
            <strong>{{ room }}室</strong>
            <label class="occupancy-control"><input type="checkbox" :checked="environment[room.toLowerCase() + 'Occupied']" @change="environmentChange(room.toLowerCase() + 'Occupied', $event.target.checked)">人がいる</label>
            <label class="co2-control">CO₂濃度
              <div><input type="number" min="0" max="10000" step="1" :aria-label="`${room}室のCO₂濃度`" :value="environment[room.toLowerCase() + 'Co2']" @change="environmentChange(room.toLowerCase() + 'Co2', Number($event.target.value))"><span>ppm</span></div>
            </label>
          </div>
        </div>
        <label class="occupancy-control"><input type="checkbox" :checked="environment.maintenance" @change="environmentChange('maintenance', $event.target.checked)">点検モード</label>
      </div>

      <div v-if="!finished" class="step-box">
        <button type="button" class="btn-next-phase step-button" :disabled="result.trace.length >= 200" @click="emit('step')">1分進める（{{ result.trace.length + 1 }}分目）→</button>
        <p class="lab-muted small">押すたびに1分進みます。上の状況をプログラムが読み取り、装置の動作を決めて、その1分間動かします。</p>
      </div>
      <p v-else class="lab-notice">このテストケースは最後まで実行しました。別のテストケースを選ぶか、プログラムを直して「最初から」確かめよう。</p>
    </fieldset>

    <div v-if="latest" class="execution-feedback" :class="latest.constraints_met ? 'is-correct' : 'is-different'" role="status">
      <div class="feedback-head">
        <strong>{{ latest.step }}分目：{{ outputLabel(latest.after.output) }}</strong>
        <span class="feedback-status">{{ latest.constraints_met ? '制限は守れています' : '制限違反' }}</span>
      </div>
      <p v-for="violation in latest.violations" :key="violation" class="violation-text">⚠ {{ violation }}</p>
      <p v-if="latest.observation.maintenance_excluded" class="small">点検中のため、換気への対応機会から除いています。</p>
      <p v-else-if="latest.observation.unserved_rooms.length" class="small">放置された部屋：{{ latest.observation.unserved_rooms.join('・') }}室（有人・1,000ppm以上で換気されなかった）</p>
      <p class="small">どのルールが使われたかは、プログラム欄に <span class="fired-chip">使用</span> で表示しています。</p>
      <details>
        <summary>内部の状態をくわしく見る</summary>
        <table class="scenario-table state-comparison"><thead><tr><th>実行後</th><th>A室</th><th>B室</th></tr></thead>
          <tbody>
            <tr><td>換気要求</td><td>{{ latest.after.demand.A ? 'ON' : 'OFF' }}</td><td>{{ latest.after.demand.B ? 'ON' : 'OFF' }}</td></tr>
            <tr><td>要求待ち時間（ルールで使える値）</td><td>{{ latest.after.wait.A }}</td><td>{{ latest.after.wait.B }}</td></tr>
            <tr><td>放置時間（評価に使う参考待ち時間）</td><td>{{ latest.observation.goal_wait.A }}</td><td>{{ latest.observation.goal_wait.B }}</td></tr>
          </tbody>
        </table>
        <p class="small">続けて運転した時間：{{ latest.after.run }}分。要求待ち時間は自分が要求をONにした部屋で増えます。放置時間は要求とは関係なく、有人・1,000ppm以上で換気されないと増え、換気・無人・1,000未満・点検で0に戻ります。</p>
      </details>
    </div>

    <div v-if="result.trace.length && result.achievement" class="trace-wrap">
      <h3 class="env-group-label">目標の達成状況 <small class="lab-muted">（ここまで実行した範囲）</small></h3>
      <ul class="goal-badges">
        <li v-for="check in result.achievement.checks" :key="check.id" :class="check.met ? 'met' : 'unmet'">
          <span aria-hidden="true">{{ check.met ? '✓' : '✗' }}</span>{{ check.label }}<small>実測 {{ check.actual }}</small>
        </li>
      </ul>
      <p class="lab-muted small">{{ finished ? 'このテストケースを最後まで確認しました。他のテストケースでも確かめよう。' : scenario ? '途中の確認です。最後まで実行しよう。' : '自分で作ったテストケースの、ここまでの範囲での確認です。' }}</p>
      <p class="lab-muted small improvement-line">改善目標：1,500ppm以上の部屋の放置 延べ <strong>{{ result.metrics.urgent_unserved_room_steps }}</strong> 分
        <template v-if="result.comparison?.comparable">（修正前 {{ result.comparison.previous }} → 今回 {{ result.comparison.current }}：{{ result.comparison.already_zero ? '両方0で改善の余地なし' : result.comparison.reduced ? '減りました' : result.comparison.current === result.comparison.previous ? '変化なし' : '増えました' }}）</template>
      </p>

      <h3 class="env-group-label">濃度の推移と装置の動作</h3>
      <VentilationTimeline :trace="result.trace" :total-steps="scenario?.steps.length || 0" />

      <details class="sim-details">
        <summary>実行の履歴を表で見る</summary>
        <div class="table-scroll"><table class="scenario-table trace-table"><thead><tr><th>#</th><th>A濃度</th><th>B濃度</th><th>動作</th><th>放置 A / B</th><th>装置制限</th></tr></thead>
          <tbody><tr v-for="row in result.trace" :key="row.step" :class="{ 'trace-mismatch': !row.constraints_met }">
            <td>{{ row.step }}</td><td>{{ row.input.aCo2 }}<small v-if="!row.input.aOccupied">無人</small></td><td>{{ row.input.bCo2 }}<small v-if="!row.input.bOccupied">無人</small></td>
            <td>{{ outputLabel(row.after.output) }}<small v-if="row.input.maintenance">点検</small></td><td>{{ row.observation.goal_wait.A }} / {{ row.observation.goal_wait.B }}</td><td>{{ row.constraints_met ? '違反なし' : '違反あり' }}</td>
          </tr></tbody></table></div>
      </details>
      <details class="sim-details">
        <summary>その他の数値を見る</summary>
        <p class="lab-muted small">1,000ppm以上の部屋への対応：{{ result.metrics.served_room_steps }} / {{ result.metrics.needs_room_steps }} 分<br>放置：延べ {{ result.metrics.unserved_room_steps }} 分（うち1,500以上：{{ result.metrics.urgent_unserved_room_steps }}）<br>放置時間の最大：A室 {{ result.metrics.max_wait.A }} ／ B室 {{ result.metrics.max_wait.B }} 分<br>無人への運転：{{ result.metrics.unoccupied_ventilation_steps }} 分 ／ 1,000未満の有人室への運転：{{ result.metrics.below_guidance_ventilation_steps }} 分</p>
        <p class="lab-muted small">801〜999ppmでの運転は禁止していません。延べの時間は、両室が同時に放置された1分を2分と数えます。</p>
        <p v-if="!result.comparison?.comparable" class="lab-muted small">{{ result.comparison ? '修正前と入力または実行した時間が異なるため、改善目標はまだ比較できません。' : '実行後にプログラムを修正すると、修正前の実行を比較用に保持します。' }}</p>
      </details>
    </div>
    <div v-else class="simulation-empty">ルールを作ったら、「1分進める」を押して動きを確かめよう。</div>
  </section>
</template>
