const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001'

async function requestJson(path, options) {
  const response = await fetch(`${API_BASE_URL}${path}`, options)
  if (!response.ok) throw new Error(`${path}: ${response.status}`)
  return response.json()
}

function jsonOptions(method, body) {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }
}

export function saveSessionLog(entry) {
  return requestJson('/api/log', jsonOptions('POST', entry))
}

export function fetchLogs() {
  return requestJson('/api/log/export')
}

export function fetchPrompts() {
  return requestJson('/api/config/prompts')
}

export function savePrompts(prompts) {
  return requestJson('/api/config/prompts', jsonOptions('POST', prompts))
}

export function resetPrompts() {
  return requestJson('/api/config/prompts/reset', jsonOptions('POST'))
}

export function fetchAdvice(payload) {
  return requestJson('/api/advice', jsonOptions('POST', payload))
}

export async function streamGroupDiscussion(payload, onTurn) {
  const response = await fetch(
    `${API_BASE_URL}/api/group-discussion/stream`,
    jsonOptions('POST', payload),
  )
  if (!response.ok) throw new Error(`group discussion API: ${response.status}`)
  if (!response.body) throw new Error('group discussion stream is unavailable')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const consumeLine = async (line) => {
    if (line.trim()) await onTurn(JSON.parse(line))
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) await consumeLine(line)
    if (done) break
  }
  await consumeLine(buffer)
}
