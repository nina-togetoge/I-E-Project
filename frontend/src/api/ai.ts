/**
 * AI 助手相关接口
 *
 * 仅封装大模型对话能力，后端 /api/ai/chat 转发到智能助手服务。
 * 调用方：components/AIAssistant.vue（悬浮助手），需要登录态，
 * 由请求拦截器统一携带 Token 与错误提示；无本地缓存。
 */
import { post } from '@/utils/request'

/**
 * 对话消息：遵循 OpenAI Chat Completions 的角色约定。
 * system 用于注入平台业务背景，user/assistant 为多轮问答历史。
 */
export interface ChatMessage {
  /** 角色：system 系统设定 / user 用户 / assistant 助手回复 */
  role: 'system' | 'user' | 'assistant'
  /** 消息文本，前端不拼接 HTML，后端按纯文本处理 */
  content: string
}

/**
 * AI 对话 POST /api/ai/chat
 * @param messages 完整上下文消息数组（前端负责裁剪历史轮次，避免超长）
 * @param temperature 采样温度，默认 0.7；越低回答越稳定
 * @returns { reply } 助手回复文本
 * 调用方：AIAssistant.vue；后端异常时由拦截器弹出提示，调用方负责占位回复。
 */
export function aiChat(messages: ChatMessage[], temperature = 0.7) {
  return post<{ reply: string }>('/api/ai/chat', { messages, temperature })
}
