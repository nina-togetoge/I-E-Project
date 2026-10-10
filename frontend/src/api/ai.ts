/**
 * AI 助手相关接口
 */
import { post } from '@/utils/request'

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

/** AI 对话 */
export function aiChat(messages: ChatMessage[], temperature = 0.7) {
  return post<{ reply: string }>('/api/ai/chat', { messages, temperature })
}
