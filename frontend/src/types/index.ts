export type MessageRole = 'user' | 'assistant'

export interface ArticleSource {
  chunk_id: string
  source: string
  article_number: string
  article_title: string
  text: string
  topics: string[]
  book: string
  chapter: string
  rerank_score: number
  derogated: boolean
  modified_by: string
  effective_date: string
}

export interface Message {
  id: string
  role: MessageRole
  content: string
  sources?: ArticleSource[]
  isStreaming?: boolean
  error?: string
  timestamp: Date
}

export interface Conversation {
  id: string
  title: string
  messages: Message[]
  createdAt: Date
  updatedAt: Date
}
