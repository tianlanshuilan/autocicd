const API_BASE = '/api'
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`

export async function generateConfig(payload) {
  const res = await fetch(`${API_BASE}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function generateFiles(payload) {
  const res = await fetch(`${API_BASE}/generate-files`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function getSteps() {
  const res = await fetch(`${API_BASE}/steps`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function startAutoDeploy(payload) {
  const res = await fetch(`${API_BASE}/auto-deploy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function getRecommendations(payload) {
  const res = await fetch(`${API_BASE}/recommendations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export function connectPipelineWs(taskId, handlers) {
  const ws = new WebSocket(`${WS_BASE}/ws/pipeline/${taskId}`)

  ws.onopen = () => {
    if (handlers.onOpen) handlers.onOpen()
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (handlers.onMessage) handlers.onMessage(data)
    } catch (e) {
      console.error('WebSocket 消息解析失败:', e)
    }
  }

  ws.onerror = (error) => {
    if (handlers.onError) handlers.onError(error)
  }

  ws.onclose = (event) => {
    if (handlers.onClose) handlers.onClose(event)
  }

  return {
    sendCredential(credType, credential) {
      ws.send(JSON.stringify({
        type: 'credential',
        cred_type: credType,
        credential
      }))
    },
    cancel() {
      ws.send(JSON.stringify({ type: 'cancel' }))
    },
    close() {
      ws.close()
    }
  }
}
