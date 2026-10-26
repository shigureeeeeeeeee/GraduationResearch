<script setup>
import { computed } from 'vue'

const props = defineProps({
  trace: { type: Array, required: true },
  totalSteps: { type: Number, default: 0 },
})

const ROOMS = ['A', 'B']
const CHART = { left: 34, right: 352, top: 10, bottom: 118, min: 600, max: 1800 }
const thresholds = [800, 1000, 1500]
const columns = computed(() => Math.max(props.totalSteps, props.trace.length, 6))
const stepX = (index) => CHART.left + (index + 0.5) * (CHART.right - CHART.left) / columns.value
const co2Y = (co2) => {
  const clamped = Math.min(CHART.max, Math.max(CHART.min, co2))
  return CHART.bottom - (clamped - CHART.min) / (CHART.max - CHART.min) * (CHART.bottom - CHART.top)
}
const cellWidth = computed(() => (CHART.right - CHART.left) / columns.value - 2)
const short = (output) => (output === 'stop' ? '停' : output)
const lines = computed(() => ROOMS.map((room) => {
  const key = room.toLowerCase()
  const points = props.trace.map((row, index) => ({ x: stepX(index), y: co2Y(row.input[key + 'Co2']), occupied: row.input[key + 'Occupied'] }))
  return { room, points, path: points.map((p) => `${p.x},${p.y}`).join(' ') }
}))
</script>

<template>
  <div class="timeline">
    <svg viewBox="0 0 376 156" role="img" aria-label="1分ごとのCO₂濃度と装置の動作">
      <g v-for="value in thresholds" :key="value" class="threshold">
        <line :x1="CHART.left" :x2="CHART.right" :y1="co2Y(value)" :y2="co2Y(value)" />
        <text :x="CHART.left - 4" :y="co2Y(value) + 3">{{ value }}</text>
      </g>
      <g v-for="line in lines" :key="line.room" :class="`series series-${line.room}`">
        <polyline :points="line.path" />
        <circle v-for="(p, i) in line.points" :key="i" :cx="p.x" :cy="p.y" r="3" :class="{ empty: !p.occupied }" />
      </g>
      <text :x="CHART.left" y="135" class="row-label" dx="-4">動作</text>
      <text x="4" y="8" class="row-label" style="text-anchor: start">ppm</text>
      <g v-for="(row, index) in trace" :key="row.step">
        <rect :x="stepX(index) - cellWidth / 2" y="124" :width="cellWidth" height="15" rx="3"
          :class="[`cell out-${row.after.output}`, { violated: !row.constraints_met, maintenance: row.input.maintenance }]" />
        <text :x="stepX(index)" y="135" class="cell-text">{{ short(row.after.output) }}</text>
        <text :x="stepX(index)" y="151" class="step-number">{{ row.step }}</text>
      </g>
      <text :x="CHART.right + 4" y="151" class="row-label" style="text-anchor: start">分目</text>
    </svg>
    <ul class="co2-legend">
      <li><span class="line-swatch series-A" />A室の濃度</li>
      <li><span class="line-swatch series-B" />B室の濃度</li>
      <li><span class="dot-swatch" />白丸＝無人</li>
      <li><span class="swatch violated-swatch" />制限違反</li>
    </ul>
  </div>
</template>
