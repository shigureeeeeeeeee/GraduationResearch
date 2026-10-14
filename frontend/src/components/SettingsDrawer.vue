<script setup>
import { computed, reactive, ref } from 'vue'
import * as legacyApi from '../services/api'
import * as ventilationApi from '../services/ventilationApi'

const props = defineProps({ task: { type: String, default: 'legacy' } })
const api = computed(() => props.task === 'ventilation' ? ventilationApi : legacyApi)

const PROMPT_FIELDS = [
  { key: 'base', label: '共通ベースプロンプト' },
  { key: 'phase2_extra', label: 'フェーズ2「ペアで対話」追加指示' },
  { key: 'phase3_extra', label: 'フェーズ3「実行して確認」追加指示' },
  { key: 'phase4_extra', label: 'フェーズ4「全体で対話」追加指示' },
]

const isOpen = ref(false)
const activeTab = ref('prompts')
const isSaving = ref(false)
const settingsMessage = ref('')
const isDashboardLoading = ref(false)
const dashboardMessage = ref('')
const logEntries = ref([])
const prompts = reactive({
  base: '',
  phase2_extra: '',
  phase3_extra: '',
  phase4_extra: '',
})

const sessionRows = computed(() => {
  const latestBySession = new Map()
  for (const entry of logEntries.value) {
    const current = latestBySession.get(entry.session_id)
    if (!current || new Date(entry.timestamp) > new Date(current.timestamp)) {
      latestBySession.set(entry.session_id, entry)
    }
  }
  return [...latestBySession.values()]
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .map((entry) => {
      const history = entry.chat_history || []
      return {
        ...entry,
        shortId: entry.session_id.slice(-8),
        finished: entry.event === 'session_end',
        ruleCount: entry.program ? Object.values(entry.program).flat().length : (entry.rules || []).length,
        chatCount: history.length,
        userChatCount: history.filter((message) => message.role === 'user').length,
        timestampLabel: new Date(entry.timestamp).toLocaleString('ja-JP'),
      }
    })
})

const dashboardSummary = computed(() => {
  const rows = sessionRows.value
  const total = rows.length
  return {
    total,
    completed: rows.filter((row) => row.finished).length,
    allCorrect: rows.filter((row) => props.task === 'ventilation'
      ? row.task_id === 'ventilation-goals-v3' && row.goals_met
      : row.all_correct).length,
    avgChat: total
      ? (rows.reduce((sum, row) => sum + row.chatCount, 0) / total).toFixed(1)
      : '0.0',
  }
})

async function open() {
  isOpen.value = true
  settingsMessage.value = ''
  dashboardMessage.value = ''
  try {
    Object.assign(prompts, await api.value.fetchPrompts())
    await loadDashboard()
  } catch {
    settingsMessage.value = 'プロンプト設定の読み込みに失敗しました'
  }
}

async function loadDashboard() {
  isDashboardLoading.value = true
  dashboardMessage.value = ''
  try {
    logEntries.value = await api.value.fetchLogs()
  } catch {
    dashboardMessage.value = 'ログの読み込みに失敗しました'
  } finally {
    isDashboardLoading.value = false
  }
}

async function persistPrompts() {
  isSaving.value = true
  settingsMessage.value = ''
  try {
    const result = await api.value.savePrompts({ ...prompts })
    if (result.status === 'ok') settingsMessage.value = '保存しました'
  } catch {
    settingsMessage.value = '保存に失敗しました'
  } finally {
    isSaving.value = false
  }
}

async function restorePrompts() {
  if (!confirm('プロンプトをデフォルトに戻しますか？')) return
  isSaving.value = true
  try {
    await api.value.resetPrompts()
    Object.assign(prompts, await api.value.fetchPrompts())
    settingsMessage.value = 'デフォルトに戻しました'
  } catch {
    settingsMessage.value = 'リセットに失敗しました'
  } finally {
    isSaving.value = false
  }
}

function download(content, type, filename) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function downloadJson() {
  download(
    JSON.stringify(logEntries.value, null, 2),
    'application/json',
    `experiment-logs-${new Date().toISOString().slice(0, 10)}.json`,
  )
}

function escapeCsv(value) {
  const text = value == null ? '' : String(value)
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function downloadCsv() {
  const headers = [
    'session_id', 'final_phase', 'finished', 'all_correct', 'rule_count',
    'chat_count', 'user_chat_count', 'last_saved_at', 'task_id', 'constraints_met',
    'unserved_room_steps', 'max_wait_a', 'max_wait_b',
    'goals_met', 'unnecessary_ventilation_steps', 'urgent_unserved_room_steps',
  ]
  const rows = sessionRows.value.map((row) => [
    row.session_id, row.phase, row.finished, row.all_correct, row.ruleCount,
    row.chatCount, row.userChatCount, row.timestamp, row.task_id, row.constraints_met,
    row.evaluation?.metrics?.unserved_room_steps, row.evaluation?.metrics?.max_wait?.A,
    row.evaluation?.metrics?.max_wait?.B,
    row.goals_met, row.evaluation?.metrics?.unnecessary_ventilation_steps,
    row.evaluation?.metrics?.urgent_unserved_room_steps,
  ])
  const csv = [headers, ...rows]
    .map((row) => row.map(escapeCsv).join(','))
    .join('\n')
  download(
    `\uFEFF${csv}`,
    'text/csv;charset=utf-8',
    `experiment-summary-${new Date().toISOString().slice(0, 10)}.csv`,
  )
}
</script>

<template>
  <button class="settings-fab" title="実験者設定" @click="open">&#9881;</button>

  <transition name="drawer">
    <div v-if="isOpen" class="settings-overlay" @click.self="isOpen = false">
      <div class="settings-drawer">
        <div class="settings-header">
          <h2 class="settings-title">実験者設定</h2>
          <button class="settings-close" @click="isOpen = false">×</button>
        </div>
        <div class="settings-tabs">
          <button class="settings-tab" :class="{ active: activeTab === 'prompts' }" @click="activeTab = 'prompts'">
            AIプロンプト
          </button>
          <button class="settings-tab" :class="{ active: activeTab === 'dashboard' }" @click="activeTab = 'dashboard'; loadDashboard()">
            ログダッシュボード
          </button>
        </div>
        <p class="settings-note">
          <template v-if="activeTab === 'prompts'">
            ここで編集したプロンプトはバックエンドに保存され、次のAI応答から反映されます。
          </template>
          <template v-else>
            保存された実験ログから、セッション数や{{ task === 'ventilation' ? '達成基準の確認状況' : '正解状況' }}、AIとの会話数を確認できます。
          </template>
        </p>

        <div v-if="activeTab === 'prompts'" class="settings-body">
          <div v-for="field in PROMPT_FIELDS" :key="field.key" class="prompt-block">
            <label class="prompt-label">{{ field.label }}</label>
            <textarea v-model="prompts[field.key]" class="prompt-textarea" rows="8" spellcheck="false" />
          </div>
        </div>

        <div v-else class="settings-body dashboard-body">
          <div class="dashboard-actions">
            <button class="btn-reset-prompt" :disabled="isDashboardLoading" @click="loadDashboard">
              {{ isDashboardLoading ? '読み込み中...' : '再読み込み' }}
            </button>
            <button class="btn-save-prompt" :disabled="logEntries.length === 0" @click="downloadJson">JSONをダウンロード</button>
            <button class="btn-save-prompt" :disabled="sessionRows.length === 0" @click="downloadCsv">CSVをダウンロード</button>
          </div>
          <div v-if="dashboardMessage" class="dashboard-error">{{ dashboardMessage }}</div>
          <div class="dashboard-summary-grid">
            <div class="dashboard-card"><span class="dashboard-card-label">セッション数</span><strong>{{ dashboardSummary.total }}</strong></div>
            <div class="dashboard-card"><span class="dashboard-card-label">完了セッション</span><strong>{{ dashboardSummary.completed }}</strong></div>
            <div class="dashboard-card"><span class="dashboard-card-label">{{ task === 'ventilation' ? '数値基準・最終実行範囲で達成' : '全シナリオ正解' }}</span><strong>{{ dashboardSummary.allCorrect }}</strong></div>
            <div class="dashboard-card"><span class="dashboard-card-label">平均会話数</span><strong>{{ dashboardSummary.avgChat }}</strong></div>
          </div>
          <div v-if="sessionRows.length === 0" class="dashboard-empty">
            まだ保存されたログがありません。フェーズ移動またはセッション完了時にログが保存されます。
          </div>
          <div v-else class="dashboard-table-wrap">
            <table class="dashboard-table">
              <thead><tr><th>セッション</th><th>最終フェーズ</th><th>状態</th><th>{{ task === 'ventilation' ? '確認状況' : '正解' }}</th><th>ルール</th><th>会話</th><th>最終保存</th></tr></thead>
              <tbody>
                <tr v-for="row in sessionRows" :key="row.session_id">
                  <td>#{{ row.shortId }}</td><td>{{ row.phase }}</td><td>{{ row.finished ? '完了' : '途中' }}</td>
                  <td v-if="row.task_id === 'ventilation-goals-v3'"><span :class="row.goals_met ? 'dash-ok' : 'dash-ng'">{{ row.goals_met ? '実行範囲で達成' : row.goals_met === null ? '未実行' : '未達' }}</span></td>
                  <td v-else-if="row.task_id === 'ventilation-goals-v2'"><span :class="row.constraints_met ? 'dash-ok' : 'dash-ng'">{{ row.constraints_met ? '旧課題：制約違反なし' : '旧課題：未実行・違反あり' }}</span></td>
                  <td v-else><span :class="row.all_correct ? 'dash-ok' : 'dash-ng'">{{ task === 'ventilation' ? '旧判定：' : '' }}{{ row.all_correct ? '正解' : '未達' }}</span></td>
                  <td>{{ row.ruleCount }}</td><td>{{ row.chatCount }}</td><td>{{ row.timestampLabel }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="activeTab === 'prompts'" class="settings-footer">
          <span v-if="settingsMessage" class="settings-msg">{{ settingsMessage }}</span>
          <button class="btn-reset-prompt" :disabled="isSaving" @click="restorePrompts">デフォルトに戻す</button>
          <button class="btn-save-prompt" :disabled="isSaving" @click="persistPrompts">{{ isSaving ? '保存中...' : '保存する' }}</button>
        </div>
      </div>
    </div>
  </transition>
</template>
