<script setup>
import { computed } from 'vue'

const props = defineProps({
  config: { type: Object, required: true },
  environment: { type: Object, required: true },
  result: { type: Object, required: true },
  program: { type: Object, required: true },
  scenarioId: { type: String, required: true },
  predictions: { type: Array, required: true },
  prediction: { type: String, required: true },
  predictionReason: { type: String, required: true },
  disabled: Boolean,
})
const emit = defineEmits(['environment', 'scenario', 'step', 'reset', 'prediction', 'prediction-reason'])
const outputLabel = (value) => ({ A: 'A室を換気', B: 'B室を換気', stop: '停止' }[value])
const scenario = computed(() => props.config.scenarios.find((item) => item.id === props.scenarioId))
const finished = computed(() => scenario.value && props.result.trace.length >= scenario.value.steps.length)
const latest = computed(() => props.result.trace.at(-1))
function environmentChange(key, value) {
  if (key.endsWith('Co2')) value = Number.isFinite(value) ? Math.min(10000, Math.max(0, Math.round(value))) : 0
  emit('environment', { ...props.environment, [key]: value })
}
function ruleNumber(stage, id) {
  const index = props.program[stage].findIndex((rule) => rule.id === id)
  return index < 0 ? '該当なし' : `ルール${index + 1}`
}
</script>

<template>
  <section class="panel panel-simulation simulation-lab">
    <div class="panel-title-row">
      <h2 class="panel-title">シミュレーション</h2>
      <span class="lab-muted small">{{ result.trace.length }} ステップ実行</span>
    </div>
    <fieldset :disabled="disabled" class="program-fieldset">
      <div class="scenario-controls">
        <label>検証する経過
          <select :value="scenarioId" aria-label="検証シナリオ" @change="emit('scenario', $event.target.value)">
            <option v-for="item in config.scenarios" :key="item.id" :value="item.id">{{ item.label }}（{{ item.steps.length }}ステップ）</option>
            <option value="custom">自分で入力する</option>
          </select>
        </label>
        <button type="button" class="env-btn" @click="emit('reset')">最初から</button>
      </div>
      <p class="lab-muted small">{{ scenario?.description || '人の有無や濃度を変えて、確かめたい経過を作れます。' }}</p>
      <div class="room-grid">
        <article v-for="room in ['A', 'B']" :key="room" class="room-card" :class="{ 'room-active': result.state.output === room }">
          <div class="room-heading"><h3>{{ room }}室</h3><span>{{ result.state.output === room ? '換気中' : '換気なし' }}</span></div>
          <label class="occupancy-control"><input type="checkbox" :checked="environment[room.toLowerCase() + 'Occupied']" @change="environmentChange(room.toLowerCase() + 'Occupied', $event.target.checked)">人がいる</label>
          <label class="co2-control">次のCO₂濃度
            <div><input type="number" min="0" max="10000" step="1" :aria-label="`${room}室のCO₂濃度`" :value="environment[room.toLowerCase() + 'Co2']" @change="environmentChange(room.toLowerCase() + 'Co2', Number($event.target.value))"><span>ppm</span></div>
          </label>
          <div class="room-state"><span>換気要求 <strong>{{ result.state.demand[room] ? 'ON' : 'OFF' }}</strong></span><span>要求待ち時間 <strong>{{ result.state.wait[room] }}</strong></span></div>
        </article>
      </div>
      <div class="fan-state" :class="{ running: result.state.output !== 'stop' }">
        <div><strong>{{ outputLabel(result.state.output) }}</strong><span>直前の動作 · 連続運転 {{ result.state.run }} ステップ</span></div>
        <label><input type="checkbox" :checked="environment.maintenance" @change="environmentChange('maintenance', $event.target.checked)">点検モード</label>
      </div>
      <p class="lab-muted small">数値と人の有無は次に実行する入力です。要求・待ち時間・装置動作は実行済みの状態です。1ステップ＝1分。</p>
      <div class="prediction-box">
        <label>このプログラムは、次にどう動くと思う？
          <select :value="prediction" aria-label="次の動作の予想" @change="emit('prediction', $event.target.value)">
            <option value="" disabled>実行前に予想を選ぶ</option><option value="A">A室を換気</option><option value="B">B室を換気</option><option value="stop">停止</option>
          </select>
        </label>
        <input :value="predictionReason" maxlength="5000" aria-label="予想の理由" placeholder="そう予想した理由（任意）" @input="emit('prediction-reason', $event.target.value)">
        <button type="button" class="btn-next-phase step-button" :disabled="!prediction || finished || result.trace.length >= 200" @click="emit('step')">{{ finished ? 'このシナリオを実行しました' : `ステップ ${result.trace.length + 1} を実行 →` }}</button>
      </div>
    </fieldset>
    <p v-if="finished" class="lab-notice">経過を見直すか、別のシナリオを選んで検証を続けられます。</p>
    <div v-if="latest" class="execution-feedback" :class="latest.constraints_met ? 'is-correct' : 'is-different'" role="status">
      <strong>{{ latest.constraints_met ? 'このステップは装置の制限に違反していません' : '装置の制限への違反が見つかりました' }}</strong>
      <p v-for="violation in latest.violations" :key="violation">{{ violation }}</p>
      <p class="small">予想：{{ outputLabel(predictions.at(-1)?.output) }} ／ 実際：{{ outputLabel(latest.after.output) }}</p>
      <p v-if="latest.observation.maintenance_excluded" class="small">点検中のため、換気への対応機会から除いています。</p>
      <p v-else-if="latest.observation.unserved_rooms.length" class="small">濃度の目安以上で換気を受けなかった部屋：{{ latest.observation.unserved_rooms.join('・') }}室。停止の制限や自分の優先方針と照らし合わせて検討しよう。</p>
      <details>
        <summary>使われたルールと内部状態を見る</summary>
        <p class="small">要求 A：{{ ruleNumber('demand', latest.fired.demand.A) }} ／ B：{{ ruleNumber('demand', latest.fired.demand.B) }}<br>選択：{{ ruleNumber('selection', latest.fired.selection) }} → {{ outputLabel(latest.candidate) }}<br>命令：{{ ruleNumber('output', latest.fired.output) }}</p>
        <table class="scenario-table state-comparison"><thead><tr><th>実行後の状態</th><th>自分のプログラム</th></tr></thead>
          <tbody><template v-for="room in ['A', 'B']" :key="room">
            <tr><td>{{ room }}室の要求</td><td>{{ latest.after.demand[room] ? 'ON' : 'OFF' }}</td></tr>
            <tr><td>{{ room }}室の要求待ち時間</td><td>{{ latest.after.wait[room] }}</td></tr>
            <tr><td>{{ room }}室の参考待ち時間</td><td>{{ latest.observation.goal_wait[room] }}</td></tr>
          </template><tr><td>連続運転数</td><td>{{ latest.after.run }}</td></tr></tbody>
        </table>
        <p class="small">参考待ち時間は自分の要求とは別に、有人かつ濃度1,000以上で有効な換気を受けなかった時間を数えます。換気・無人・1,000未満・点検で0に戻ります。</p>
      </details>
    </div>
    <div v-if="result.trace.length" class="trace-wrap">
      <div class="trace-heading"><h3>実行の履歴</h3><span>制約違反 {{ result.metrics.violation_steps }} ステップ</span></div>
      <div class="table-scroll"><table class="scenario-table trace-table"><thead><tr><th>#</th><th>A濃度</th><th>B濃度</th><th>予想</th><th>動作</th><th>参考待ち A / B</th><th>装置制限</th></tr></thead>
        <tbody><tr v-for="row in result.trace" :key="row.step" :class="{ 'trace-mismatch': !row.constraints_met }">
          <td>{{ row.step }}</td><td>{{ row.input.aCo2 }}<small v-if="!row.input.aOccupied">無人</small></td><td>{{ row.input.bCo2 }}<small v-if="!row.input.bOccupied">無人</small></td>
          <td>{{ predictions[row.step - 1]?.output === 'stop' ? '停止' : predictions[row.step - 1]?.output }}</td>
          <td>{{ row.after.output === 'stop' ? '停止' : row.after.output }}<small v-if="row.input.maintenance">点検</small></td><td>{{ row.observation.goal_wait.A }} / {{ row.observation.goal_wait.B }}</td><td>{{ row.constraints_met ? '違反なし' : '違反あり' }}</td>
        </tr></tbody></table></div>
      <h3 class="env-group-label">この実行範囲の達成状況</h3>
      <p v-for="check in result.achievement.checks" :key="check.id" class="lab-muted small"><strong>{{ check.label }}：{{ check.met ? '達成' : '未達' }}</strong>（実測 {{ check.actual }}）</p>
      <p class="lab-muted small">{{ finished ? 'このシナリオの全ステップで確認しました。他のシナリオも検証してください。' : scenario ? '途中の確認です。この経過の残りのステップも実行してください。' : '自分で入力した実行範囲での確認です。別の入力でも検証してください。' }} 参考待ち時間は必要な停止も含みます。</p>
      <h3 class="env-group-label">達成後の改善目標</h3>
      <p class="lab-muted small">1,500ppm以上の有人室の未対応：延べ <strong>{{ result.metrics.urgent_unserved_room_steps }}</strong> 部屋ステップ。同じ入力・同じステップ数で、修正前より減らそう。</p>
      <p v-if="result.comparison?.comparable" class="lab-muted small">修正前 {{ result.comparison.previous }} → 現在 {{ result.comparison.current }} 部屋ステップ：{{ result.comparison.already_zero ? '両案とも0（改善の余地なし）' : result.comparison.reduced ? '未対応時間が減りました' : result.comparison.current === result.comparison.previous ? '変化なし' : '未対応時間が増えました' }}。{{ result.achievement.all_met ? '達成基準も満たしています。' : '達成基準を満たす修正も必要です。' }}</p>
      <p v-else class="lab-muted small">{{ result.comparison ? '修正前と入力またはステップ数が異なるため、まだ比較できません。' : '実行後にプログラムを修正すると、修正前の実行を比較用に保持します。' }}</p>
      <h3 class="env-group-label">その他の観測指標</h3>
      <p class="lab-muted small">目安以上の部屋への対応：{{ result.metrics.served_room_steps }} / {{ result.metrics.needs_room_steps }} 部屋ステップ<br>未対応：延べ {{ result.metrics.unserved_room_steps }} 部屋ステップ（うち1,500以上：{{ result.metrics.urgent_unserved_room_steps }}）<br>参考待ち時間の最大：A室 {{ result.metrics.max_wait.A }} ／ B室 {{ result.metrics.max_wait.B }} ステップ<br>無人への運転：{{ result.metrics.unoccupied_ventilation_steps }} ／ 目安未満の有人室への運転：{{ result.metrics.below_guidance_ventilation_steps }} ステップ</p>
      <p class="lab-muted small">801〜999ppmでの運転は禁止していません。条件と優先順位をどう設計したか、理由とともに説明しよう。</p>
    </div>
    <div v-else class="simulation-empty">まず自分の方針で次の動作を予想し、1ステップ実行してみよう。<br>目的と制限に照らし合わせて検討できます。</div>
    <slot />
  </section>
</template>
