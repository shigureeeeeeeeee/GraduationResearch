<script setup>
import { computed } from 'vue'

// 次に読み取る入力（濃度・人・点検）と、ここまでの装置の状態を1枚の図で示す
const props = defineProps({
  environment: { type: Object, required: true },
  state: { type: Object, required: true },
  goalWait: { type: Object, required: true },
  nextStep: { type: Number, required: true },
  finished: Boolean,
})

const ROOMS = ['A', 'B']
const ROOM_X = { A: 12, B: 192 }
const WAIT_LIMIT = 4

// 濃度の区分は課題の基準（800以下・1,000以上・1,500以上）に合わせる
function level(co2) {
  if (co2 >= 1500) return 'urgent'
  if (co2 >= 1000) return 'high'
  if (co2 > 800) return 'middle'
  return 'low'
}
const LEVELS = [
  { id: 'low', label: '800以下' },
  { id: 'middle', label: '801〜999' },
  { id: 'high', label: '1,000〜1,499' },
  { id: 'urgent', label: '1,500以上' },
]

const rooms = computed(() => ROOMS.map((room) => {
  const key = room.toLowerCase()
  const co2 = props.environment[key + 'Co2']
  return { id: room, x: ROOM_X[room], co2, occupied: props.environment[key + 'Occupied'], level: level(co2),
    demand: props.state.demand[room], demandWait: props.state.wait[room], wait: props.goalWait[room] }
}))
const running = computed(() => props.state.output !== 'stop')
const caption = computed(() => props.finished
  ? 'このテストケースの最後の状況'
  : props.nextStep === 1 ? 'いま：開始前（次は1分目）' : `いま：${props.nextStep - 1}分経過（次は${props.nextStep}分目）`)
const summary = computed(() => rooms.value.map((room) =>
  `${room.id}室 ${room.occupied ? '有人' : '無人'} ${room.co2}ppm 放置${room.wait}分`).join('、')
  + `、装置は${running.value ? `${props.state.output}室を換気中` : '停止中'}${props.environment.maintenance ? '、点検中' : ''}`)
</script>

<template>
  <div class="ventilation-visual">
    <p class="visual-caption">{{ caption }}</p>
    <svg class="floor-plan" viewBox="0 0 376 196" role="img" :aria-label="summary">
      <g class="unit" :class="{ running, maintenance: environment.maintenance }">
        <path v-for="room in rooms" :key="'duct' + room.id" class="duct" :class="{ active: state.output === room.id }"
          :d="room.id === 'A' ? 'M122 30 H98 V62' : 'M254 30 H278 V62'" />
        <rect x="122" y="4" width="132" height="52" rx="8" class="unit-body" />
        <g class="fan" transform="translate(144 30)">
          <circle r="13" class="fan-ring" />
          <g class="fan-blades"><path d="M0 0 L-3 -11 A4 4 0 0 1 3 -11 Z M0 0 L11 -3 A4 4 0 0 1 11 3 Z M0 0 L3 11 A4 4 0 0 1 -3 11 Z M0 0 L-11 3 A4 4 0 0 1 -11 -3 Z" /></g>
        </g>
        <text x="206" y="21" class="unit-label">換気装置</text>
        <text x="206" y="36" class="unit-sub">{{ running ? `${state.output}室を換気中` : '停止中' }}</text>
        <text x="206" y="50" class="unit-sub">連続運転 {{ state.run }}/2分</text>
        <text v-if="environment.maintenance" x="262" y="20" class="maintenance-label">🔧 点検中</text>
      </g>
      <g v-for="room in rooms" :key="room.id" :transform="`translate(${room.x} 62)`" class="room" :class="[`co2-${room.level}`, { active: state.output === room.id }]">
        <rect width="172" height="126" rx="8" class="room-body" />
        <g v-if="state.output === room.id" class="airflow">
          <path d="M86 4 V34" /><path d="M68 6 Q62 22 68 36" /><path d="M104 6 Q110 22 104 36" />
        </g>
        <text x="10" y="20" class="room-name">{{ room.id }}室</text>
        <text x="162" y="18" class="room-demand" :class="{ on: room.demand }">前回の要求 {{ room.demand ? 'ON' : 'OFF' }}</text>
        <text x="162" y="31" class="room-demand">要求待ち時間 {{ room.demandWait }}分</text>
        <text x="86" y="62" class="room-co2">{{ room.co2.toLocaleString() }}<tspan class="unit-ppm"> ppm</tspan></text>
        <g v-if="room.occupied" class="people" transform="translate(64 72)">
          <g v-for="n in 3" :key="n" :transform="`translate(${(n - 1) * 22} 0)`">
            <circle cx="0" cy="5" r="5" /><path d="M-7 22 Q-7 11 0 11 Q7 11 7 22 Z" />
          </g>
        </g>
        <text v-else x="86" y="88" class="room-empty">無人</text>
        <g class="wait-gauge" transform="translate(10 104)">
          <text x="0" y="10" class="wait-label">放置</text>
          <rect v-for="n in WAIT_LIMIT" :key="n" :x="28 + (n - 1) * 16" y="1" width="13" height="11" rx="2"
            :class="{ filled: n <= room.wait, over: room.wait > WAIT_LIMIT }" />
          <text x="96" y="10" class="wait-value" :class="{ over: room.wait > WAIT_LIMIT }">{{ room.wait }} / {{ WAIT_LIMIT }} 分</text>
        </g>
      </g>
    </svg>
    <ul class="co2-legend" aria-label="CO₂濃度の色分け">
      <li v-for="item in LEVELS" :key="item.id"><span :class="`swatch co2-${item.id}`" />{{ item.label }}</li>
      <li><span class="swatch gauge-swatch" />放置：有人・1,000以上で換気されていない時間</li>
    </ul>
  </div>
</template>
