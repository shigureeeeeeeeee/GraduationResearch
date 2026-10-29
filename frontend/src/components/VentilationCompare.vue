<script setup>
import { computed } from 'vue'
import { compareSummaries, programSummary } from '../ruleText'

// フェーズ2・3：ペア（AI）の案と自分の案を段階ごとに並べ、違うところを示す
const props = defineProps({
  config: { type: Object, required: true },
  program: { type: Object, required: true },
  pair: { type: Object, default: null },
})
const stages = computed(() => props.pair
  ? compareSummaries(programSummary(props.config, props.program), programSummary(props.config, props.pair.program))
  : [])
const differentCount = computed(() => stages.value.filter((stage) => !stage.same).length)
</script>

<template>
  <details v-if="pair" class="panel compare-panel" open>
    <summary>
      <strong>ペアの案と比べる</strong>
      <span class="lab-muted small">{{ differentCount ? `${differentCount}つの段階で違う` : '3つの段階とも同じ' }}</span>
    </summary>
    <p class="lab-muted small">ペア（AI）も同じ課題を自分で考えた仲間です。この案が正しいとは限りません。<strong>違う</strong>のマークの段階が話のきっかけになります。</p>
    <div class="compare-head"><span>あなたの案</span><span>ペアの案（{{ pair.title }}）</span></div>
    <section v-for="stage in stages" :key="stage.id" class="compare-stage" :class="{ different: !stage.same }">
      <h4>{{ stage.name }}<span v-if="!stage.same" class="diff-chip">違う</span></h4>
      <div class="compare-columns">
        <ol>
          <li v-for="(rule, i) in stage.mine" :key="i" :class="{ only: !rule.shared }">{{ rule.text }}</li>
          <li v-if="!stage.mine.length" class="empty">ルールなし</li>
        </ol>
        <ol>
          <li v-for="(rule, i) in stage.theirs" :key="i" :class="{ only: !rule.shared }">{{ rule.text }}</li>
          <li v-if="!stage.theirs.length" class="empty">ルールなし</li>
        </ol>
      </div>
    </section>
    <p class="lab-muted small">色付きのルールは、片方の案にしかないものです。同じルールでも順番が違うと、動きが変わることがあります。</p>
  </details>
</template>
