<script setup>
defineProps({
  environment: { type: Object, required: true },
  result: { type: Object, required: true },
  scenarios: { type: Array, required: true },
})

const emit = defineEmits(['select-environment'])

function selectEnvironment(values) {
  emit('select-environment', values)
}
</script>

<template>
  <section class="panel panel-sim">
    <h2 class="panel-title">シミュレーション</h2>
    <p class="panel-desc">環境を選んで、プログラムの動きを確かめよう。</p>

    <div class="env-selector">
      <div class="env-row">
        <span class="env-label">時間帯</span>
        <div class="env-buttons">
          <button class="env-btn" :class="{ active: !environment.isDark }" @click="selectEnvironment({ isDark: false })">昼</button>
          <button class="env-btn" :class="{ active: environment.isDark }" @click="selectEnvironment({ isDark: true })">夜</button>
        </div>
      </div>
      <div class="env-row">
        <span class="env-label">人の有無</span>
        <div class="env-buttons">
          <button class="env-btn" :class="{ active: environment.personPresent }" @click="selectEnvironment({ personPresent: true })">人あり</button>
          <button class="env-btn" :class="{ active: !environment.personPresent }" @click="selectEnvironment({ personPresent: false })">人なし</button>
        </div>
      </div>
    </div>

    <div class="sim-scene" :class="environment.isDark ? 'scene-night' : 'scene-day'">
      <div class="scene-sky">
        <div v-if="!environment.isDark" class="sun"></div>
        <template v-else>
          <div v-for="i in 6" :key="i" class="star" :style="{ left: `${10 + i * 14}%`, top: `${8 + (i % 3) * 12}%` }"></div>
        </template>
      </div>
      <div class="scene-ground"></div>
      <div class="store-building">
        <div class="store-bell-wrap">
          <div class="store-bell" :class="{ 'bell-ringing': result.bellRinging }">
            <div class="bell-top"></div><div class="bell-body-shape"></div><div class="bell-clapper"></div>
          </div>
          <div v-if="result.bellRinging" class="bell-wave">♪</div>
        </div>
        <div class="store-sign-bar">STORE</div>
        <div class="door-frame">
          <div class="door-panel door-left" :class="{ 'door-open': result.doorOpen }"></div>
          <div class="door-panel door-right" :class="{ 'door-open': result.doorOpen }"></div>
          <div class="door-floor"></div>
        </div>
      </div>
      <transition name="person-slide">
        <div v-if="environment.personPresent" class="person-figure">
          <div class="person-head"></div><div class="person-body"></div>
          <div class="person-legs"><div class="leg left"></div><div class="leg right"></div></div>
        </div>
      </transition>
    </div>

    <div class="scenario-wrap">
      <p class="env-group-label">シナリオ切替</p>
      <table class="scenario-table">
        <thead><tr><th>状況</th><th>ドア</th><th>チャイム</th></tr></thead>
        <tbody>
          <tr
            v-for="scenario in scenarios"
            :key="scenario.label"
            :class="{ 'row-active': scenario.personPresent === environment.personPresent && scenario.isDark === environment.isDark }"
            style="cursor:pointer"
            @click="selectEnvironment({ personPresent: scenario.personPresent, isDark: scenario.isDark })"
          >
            <td>{{ scenario.label }}</td>
            <td>{{ scenario.doorOpen ? '開' : '閉' }}</td>
            <td>{{ scenario.bellRinging ? '鳴る' : '静か' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
