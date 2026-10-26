const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001') + '/api/ventilation'

async function request(path, body, { method = body === undefined ? 'GET' : 'POST', signal } = {}) {
  const response = await fetch(API_BASE + path, {
    method, signal: signal || AbortSignal.timeout(15000),
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    const details = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join(' / ')
      : data.detail
    throw new Error(details || `通信エラー (${response.status})`)
  }
  return response.json()
}

export const fetchConfig = () => request('/config')
export const simulate = (program, steps, baseline = null) => request('/simulate', { task_id: 'ventilation-goals-v3', program, steps, baseline })
export const simulateAll = (program) => request('/simulate-all', { program })
export const fetchAdvice = (payload, signal) => request('/advice', payload, { signal })
export const saveSessionLog = (payload) => request('/log', payload)
export const fetchLogs = () => request('/log/export')
export const fetchPrompts = () => request('/config/prompts')
export const savePrompts = (payload) => request('/config/prompts', payload)
export const resetPrompts = () => request('/config/prompts/reset', undefined, { method: 'POST' })

export async function streamGroupDiscussion(payload, onTurn, signal) {
  const response = await fetch(API_BASE + '/group-discussion/stream', {
    method: 'POST', signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok || !response.body) throw new Error('全体対話の開始に失敗しました。')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) if (line.trim()) await onTurn(JSON.parse(line))
      if (done) break
    }
    if (buffer.trim()) await onTurn(JSON.parse(buffer))
  } finally {
    reader.releaseLock()
  }
}
