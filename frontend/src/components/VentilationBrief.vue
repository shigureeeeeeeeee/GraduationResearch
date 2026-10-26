<script setup>
defineProps({ config: { type: Object, required: true } })

// 学習者が最初に読む要約。正式な文言は config（ventilation_content.py）を折りたたみで示す
const goals = [
  { icon: '⏱', title: '待たせすぎない', text: '人がいて 1,000ppm 以上の部屋を、4分を超えて続けて放置しない',
    note: '放置が 1分→2分→3分→4分 まではOK。5分目も換気されないと未達。換気・退室・1,000ppm未満・点検で0分に戻る。' },
  { icon: '🚫', title: 'ムダに動かさない', text: '無人の部屋や、800ppm 以下の部屋は換気しない' },
  { icon: '⚙', title: '装置の制限を守る', text: '下の4つの制限を1回も破らない' },
]
// 例は1マス＝1分の装置の動作。ventilation_engine.py の違反判定（前回の連続運転数・前回の動作）に合わせる
const limits = [
  { text: '同時に換気できるのは1部屋だけ' },
  { text: '2分続けて運転したら、次の1分は停止', ok: ['A', 'A', 'stop', 'A'], ng: ['A', 'A', 'A'] },
  { text: '別の部屋へ切り替えるときは、間に1分停止', ok: ['A', 'stop', 'B'], ng: ['A', 'B'] },
  { text: '点検中は必ず停止' },
]
const cell = (output) => (output === 'stop' ? '停' : output)
</script>

<template>
  <details class="task-brief" open>
    <summary>
      <span class="problem-label">課題</span>
      <span class="brief-lead">自習室A・Bで<strong>1台の換気装置</strong>を共有しています。下の<strong>目的と制限</strong>を満たし、<strong>8つのテストケースすべてで目的を達成する</strong>ルールを作りましょう。装置は<strong>1分ごと</strong>に「A室を換気」「B室を換気」「停止」のどれかを選びます。シミュレーションでは「1分進める」を押すたびに1分ずつ進みます。</span>
    </summary>
    <div class="brief-body">
      <div class="brief-goals">
        <article v-for="goal in goals" :key="goal.title" class="brief-card">
          <span class="brief-icon" aria-hidden="true">{{ goal.icon }}</span>
          <div><strong>{{ goal.title }}</strong><p>{{ goal.text }}</p><p v-if="goal.note" class="brief-note">{{ goal.note }}</p></div>
        </article>
      </div>
      <div class="brief-limits">
        <strong>装置の制限</strong><span class="brief-note">（例は1マス＝1分の装置の動作）</span>
        <ol>
          <li v-for="limit in limits" :key="limit.text">{{ limit.text }}
            <span v-if="limit.ok" class="minute-examples">
              <span class="minute-example ok"><span v-for="(o, i) in limit.ok" :key="i" :class="`minute-cell out-${o}`">{{ cell(o) }}</span>OK</span>
              <span class="minute-example ng"><span v-for="(o, i) in limit.ng" :key="i" :class="`minute-cell out-${o}`">{{ cell(o) }}</span>違反</span>
            </span>
          </li>
        </ol>
      </div>
      <p class="brief-hint">どちらの部屋を優先するか、いつ換気を始めて終えるかは自分で決めます。正解は1つではありません。3つの目標を満たしたら、<strong>1,500ppm以上の部屋を放置した時間</strong>を減らせないか考えよう。</p>
      <details class="brief-detail">
        <summary>くわしい規定（数え方・使える情報）</summary>
        <template v-for="section in [{ title: '数値で確認する達成基準', items: config.goals }, { title: '達成後の改善目標', items: [config.improvement] }, { title: '装置の制限', items: config.constraints }, { title: '情報と検討の目安', items: config.guidance }]" :key="section.title">
          <p><strong>{{ section.title }}</strong></p>
          <ol><li v-for="item in section.items" :key="item.title"><strong>{{ item.title }}</strong>：{{ item.text }}</li></ol>
        </template>
        <p>各段階は上から順に条件を調べ、最初に当てはまったルールを使います。「前回の要求」「待ち時間」「前回の動作」は、その1分が始まる時点の値です。CO₂濃度は入力値で、換気による変化の物理計算はしません。</p>
      </details>
    </div>
  </details>
</template>
