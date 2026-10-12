<!--
  AI 助手悬浮组件
  右下角悬浮图标，点击展开对话面板，对接豆包大模型
  支持多会话历史记录，AI 自动命名
-->
<template>
  <div class="ai-assistant">
    <!-- 对话面板 -->
    <transition name="ai-fade">
      <div v-show="visible" class="ai-panel" :class="{ 'ai-panel-min': minified }">
        <div class="ai-header">
          <div class="ai-title" @click="showHistory = !showHistory" style="cursor:pointer">
            <el-icon :size="18" color="#fff"><ChatDotRound /></el-icon>
            <span>小创助手</span>
          </div>
          <div class="ai-actions">
            <el-icon class="ai-history-btn" @click.stop="showHistory = !showHistory" :size="16" title="历史记录">
              <Tickets />
            </el-icon>
            <el-icon class="ai-min-btn" @click="minified = !minified" :size="16">
              <component :is="minified ? 'ArrowDown' : 'ArrowUp'" />
            </el-icon>
            <el-icon class="ai-close-btn" @click="visible = false" :size="16">
              <Close />
            </el-icon>
          </div>
        </div>

        <!-- 历史记录侧栏 -->
        <transition name="ai-slide">
          <div v-show="showHistory && !minified" class="ai-history">
            <div class="ai-history-head">
              <span class="ai-history-title">历史对话</span>
              <el-button type="primary" size="small" :icon="Plus" @click="newConversation" plain>新建</el-button>
            </div>
            <div class="ai-history-list">
              <div
                v-for="conv in conversations"
                :key="conv.id"
                class="ai-history-item"
                :class="{ active: conv.id === currentId }"
                @click="switchConversation(conv.id)"
              >
                <el-icon :size="14" class="ai-history-icon"><ChatDotRound /></el-icon>
                <span class="ai-history-name">{{ conv.title }}</span>
                <el-icon class="ai-history-del" :size="14" @click.stop="deleteConversation(conv.id)">
                  <Delete />
                </el-icon>
              </div>
              <div v-if="conversations.length === 0" class="ai-history-empty">暂无历史对话</div>
            </div>
          </div>
        </transition>

        <div v-show="!minified" class="ai-body" ref="bodyRef">
          <div v-for="(msg, i) in messages" :key="i" class="ai-msg" :class="msg.role">
            <div class="ai-bubble">
              <span v-if="msg.role === 'assistant' && msg.loading" class="ai-dots">
                <i></i><i></i><i></i>
              </span>
              <span v-else>{{ msg.content }}</span>
            </div>
          </div>
          <div v-if="messages.length === 1" class="ai-welcome">
            <p>👋 你好，我是小创助手！</p>
            <p>可以问我创新创业项目申报、审核、经费、比赛等问题～</p>
          </div>
        </div>

        <div v-show="!minified" class="ai-footer">
          <el-input
            v-model="input"
            type="textarea"
            :rows="1"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="输入问题，Enter 发送 / Shift+Enter 换行"
            @keydown.enter.exact.prevent="send"
            :disabled="loading"
            resize="none"
          />
          <el-button
            type="primary"
            :icon="Promotion"
            circle
            :loading="loading"
            :disabled="!input.trim()"
            @click="send"
          />
        </div>
      </div>
    </transition>

    <!-- 悬浮按钮 -->
    <div class="ai-fab" @click="toggle">
      <el-icon v-if="!visible" :size="26"><ChatDotRound /></el-icon>
      <el-icon v-else :size="22"><Close /></el-icon>
      <span v-if="!visible" class="ai-fab-tip">AI 助手</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { ChatDotRound, Close, Promotion, ArrowUp, ArrowDown, Tickets, Plus, Delete } from '@element-plus/icons-vue'
import { aiChat, type ChatMessage } from '@/api/ai'
import { ElMessage, ElMessageBox } from 'element-plus'

interface Conversation {
  id: string
  title: string
  messages: (ChatMessage & { loading?: boolean })[]
  createdAt: number
}

const STORAGE_KEY = 'ai_conversations_v1'

const visible = ref(false)
const minified = ref(false)
const showHistory = ref(false)
const loading = ref(false)
const input = ref('')
const bodyRef = ref<HTMLElement>()

const conversations = ref<Conversation[]>([])
const currentId = ref<string>('')

const currentConv = computed(() => conversations.value.find(c => c.id === currentId.value))
const messages = computed(() => currentConv.value?.messages ?? [])

/* ---------- 持久化 ---------- */
function loadConversations() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      conversations.value = JSON.parse(raw)
    }
  } catch {
    conversations.value = []
  }
  if (conversations.value.length === 0) {
    createConversation()
  } else {
    currentId.value = conversations.value[0].id
  }
}

function saveConversations() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations.value))
}

/* ---------- 会话管理 ---------- */
function createConversation(): Conversation {
  const conv: Conversation = {
    id: `c_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    title: '新对话',
    messages: [{ role: 'assistant', content: '' }],
    createdAt: Date.now(),
  }
  conversations.value.unshift(conv)
  currentId.value = conv.id
  saveConversations()
  return conv
}

function newConversation() {
  createConversation()
  showHistory.value = false
}

function switchConversation(id: string) {
  currentId.value = id
  showHistory.value = false
  scrollBottom()
}

async function deleteConversation(id: string) {
  try {
    await ElMessageBox.confirm('确定删除该对话记录？', '提示', { type: 'warning' })
  } catch {
    return
  }
  const idx = conversations.value.findIndex(c => c.id === id)
  if (idx === -1) return
  conversations.value.splice(idx, 1)
  if (currentId.value === id) {
    if (conversations.value.length > 0) {
      currentId.value = conversations.value[0].id
    } else {
      createConversation()
    }
  }
  saveConversations()
}

/* ---------- 对话 ---------- */
function toggle() {
  visible.value = !visible.value
  if (visible.value && minified.value) minified.value = false
}

function scrollBottom() {
  nextTick(() => {
    if (bodyRef.value) {
      bodyRef.value.scrollTop = bodyRef.value.scrollHeight
    }
  })
}

async function generateTitle(conv: Conversation) {
  // 仅首轮对话后自动命名
  const userMsgs = conv.messages.filter(m => m.role === 'user')
  if (userMsgs.length !== 1 || conv.title !== '新对话') return
  const firstUser = userMsgs[0].content
  try {
    const res = await aiChat([
      { role: 'user', content: `请用不超过8个字概括以下问题的主题，只返回标题，不要标点和引号：${firstUser}` },
    ], 0.3)
    const title = (res.data.reply || '').trim().slice(0, 12)
    if (title) {
      conv.title = title
      saveConversations()
    }
  } catch {
    // 命名失败不影响对话
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  input.value = ''
  const conv = currentConv.value
  if (!conv) return

  conv.messages.push({ role: 'user', content: text })
  conv.messages.push({ role: 'assistant', content: '', loading: true })
  scrollBottom()
  loading.value = true

  const history = conv.messages
    // 排除加载占位消息与空的欢迎占位消息（后端要求 content 至少 1 个字符）
    .filter(m => !m.loading && m.content && m.content.trim())
    .map(m => ({ role: m.role, content: m.content }))

  try {
    const res = await aiChat(history)
    const last = conv.messages[conv.messages.length - 1]
    last.content = res.data.reply || '（无回复内容）'
    last.loading = false
    saveConversations()
    // 首轮对话后自动命名
    generateTitle(conv)
  } catch (e: any) {
    const last = conv.messages[conv.messages.length - 1]
    last.content = '抱歉，AI 服务暂时不可用，请稍后再试。'
    last.loading = false
    ElMessage.error(e?.message || '请求失败')
  } finally {
    loading.value = false
    scrollBottom()
  }
}

onMounted(() => {
  loadConversations()
})
</script>

<style scoped>
.ai-assistant {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 9999;
}

/* 悬浮按钮 */
.ai-fab {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(64, 158, 255, 0.4);
  transition: all 0.2s ease;
  position: relative;
}
.ai-fab:hover {
  background: #337ecc;
  box-shadow: 0 6px 18px rgba(64, 158, 255, 0.5);
}
.ai-fab-tip {
  position: absolute;
  right: 60px;
  background: rgba(0, 0, 0, 0.72);
  color: #fff;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s;
}
.ai-fab:hover .ai-fab-tip {
  opacity: 1;
}

/* 对话面板 */
.ai-panel {
  position: absolute;
  right: 0;
  bottom: 68px;
  width: 360px;
  height: 520px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ai-panel-min {
  height: auto;
}

.ai-header {
  background: #409eff;
  color: #fff;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ai-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
}
.ai-actions {
  display: flex;
  gap: 12px;
}
.ai-actions .el-icon {
  cursor: pointer;
  opacity: 0.85;
  transition: opacity 0.2s;
}
.ai-actions .el-icon:hover {
  opacity: 1;
}

/* 历史记录侧栏 */
.ai-history {
  position: absolute;
  top: 0;
  left: 0;
  width: 220px;
  height: 100%;
  background: #fff;
  border-right: 1px solid #ebeef5;
  z-index: 5;
  display: flex;
  flex-direction: column;
}
.ai-history-head {
  padding: 12px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ai-history-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.ai-history-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}
.ai-history-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #606266;
  transition: background 0.15s;
  margin-bottom: 2px;
}
.ai-history-item:hover {
  background: #f5f7fa;
}
.ai-history-item.active {
  background: #ecf5ff;
  color: #409eff;
}
.ai-history-icon {
  flex-shrink: 0;
}
.ai-history-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ai-history-del {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
  color: #909399;
}
.ai-history-item:hover .ai-history-del {
  opacity: 1;
}
.ai-history-del:hover {
  color: #f56c6c !important;
}
.ai-history-empty {
  text-align: center;
  color: #c0c4cc;
  font-size: 12px;
  padding: 40px 0;
}

.ai-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  background: #f7f8fa;
}

.ai-welcome {
  color: #909399;
  font-size: 13px;
  line-height: 1.8;
  margin-top: 12px;
}

.ai-msg {
  display: flex;
  margin-bottom: 12px;
}
.ai-msg.user {
  justify-content: flex-end;
}
.ai-bubble {
  max-width: 80%;
  padding: 9px 13px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}
.ai-msg.assistant .ai-bubble {
  background: #fff;
  border: 1px solid #ebeef5;
  border-top-left-radius: 3px;
}
.ai-msg.user .ai-bubble {
  background: #409eff;
  color: #fff;
  border-top-right-radius: 3px;
}

/* 加载动画 */
.ai-dots {
  display: inline-flex;
  gap: 4px;
  padding: 2px 0;
}
.ai-dots i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #c0c4cc;
  animation: ai-bounce 1.2s infinite ease-in-out;
}
.ai-dots i:nth-child(2) { animation-delay: 0.15s; }
.ai-dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes ai-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

.ai-footer {
  padding: 12px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.ai-footer :deep(.el-textarea__inner) {
  border-radius: 10px;
}

/* 过渡动画 */
.ai-fade-enter-active,
.ai-fade-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.ai-fade-enter-from,
.ai-fade-leave-to {
  opacity: 0;
  transform: translateY(12px) scale(0.96);
}

.ai-slide-enter-active,
.ai-slide-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.ai-slide-enter-from,
.ai-slide-leave-to {
  opacity: 0;
  transform: translateX(-12px);
}
</style>
