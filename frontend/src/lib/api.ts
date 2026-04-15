// En dev: Vite proxy /api → localhost:8080 (vite.config.ts)
// En prod: VITE_API_URL=https://api.tudominio.com (sin trailing slash)
const BASE = import.meta.env.VITE_API_URL ?? '/api'

export interface ChatPayload {
  query: string
  top_k?: number
}

/** Streaming fetch — yields raw SSE lines */
export async function* streamChat(payload: ChatPayload): AsyncGenerator<string> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  yield* readSSE(res)
}

export async function* streamDocument(file: File, question: string): AsyncGenerator<string> {
  const form = new FormData()
  form.append('file', file)
  form.append('question', question)
  const res = await fetch(`${BASE}/analyze-document`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  yield* readSSE(res)
}

async function* readSSE(res: Response): AsyncGenerator<string> {
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith('data:')) {
        yield trimmed.slice(5).trim()
      }
    }
  }
}

export async function checkHealth() {
  const res = await fetch(`${BASE}/health`)
  return res.json()
}
