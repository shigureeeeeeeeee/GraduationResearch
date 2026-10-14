<script setup>
defineProps({
  phases: { type: Array, required: true },
  currentPhase: { type: Number, required: true },
  currentPhaseData: { type: Object, required: true },
  disabled: Boolean,
  completed: Boolean,
})

defineEmits(['advance', 'complete'])
</script>

<template>
  <div class="phase-bar">
    <div class="phase-bar-inner">
      <div class="phase-steps">
        <div
          v-for="phase in phases"
          :key="phase.id"
          class="phase-step"
          :class="{
            'step-done': phase.id < currentPhase,
            'step-active': phase.id === currentPhase,
            'step-future': phase.id > currentPhase,
          }"
        >
          <div class="step-circle">
            <span v-if="phase.id < currentPhase" class="step-check">✓</span>
            <span v-else>{{ phase.id }}</span>
          </div>
          <div class="step-label">{{ phase.label }}</div>
          <div v-if="phase.id < phases.length" class="step-connector" />
        </div>
      </div>
      <div class="phase-desc">{{ currentPhaseData.desc }}</div>
      <div class="phase-nav">
        <button v-if="currentPhase < 4" class="btn-next-phase" :disabled="disabled" @click="$emit('advance')">次のフェーズへ進む →</button>
        <button v-else class="btn-next-phase btn-complete" :disabled="disabled || completed" @click="$emit('complete')">{{ completed ? 'セッション保存済み' : 'セッションを完了して保存する' }}</button>
      </div>
    </div>
  </div>
</template>
