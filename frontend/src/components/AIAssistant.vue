<!--
  ==== AIAssistant ====
  职责：AI 助手悬浮组件。右下角悬浮图标，点击展开对话面板，对接后端 AI 接口（豆包大模型），
        可用于项目书润色、评审意见生成、申报流程答疑等；支持多会话、历史侧栏、
        最小化、首轮对话自动命名。
  复用：全局布局（Layout）中挂载一次即可，学生/教师/专家/管理员通用，不绑定具体页面。
  契约：无 props、无 emit、无插槽；完全自包含，会话数据存于组件状态与 localStorage。
  注意：1) 会话记录仅存浏览器 localStorage（key: ai_conversations_v1），不落后端数据库，
           换设备或清缓存后历史丢失；
        2) 发送前会过滤加载占位消息与空内容，后端要求 content 至少 1 个字符；
        3) 单轮请求失败只替换当前回复为错误提示，不影响后续提问；
        4) 首轮用户消息后用低温度请求让模型生成不超过 8 字的会话标题。
-->
<template>
  <div class="ai-assistant">
    <!-- 区块：对话面板，v-show 控制显隐，minified 时只保留标题栏 -->
    <transition name="ai-fade">
      <div v-show="visible" class="ai-panel" :class="{ 'ai-panel-min': minified }">
        <!-- 区块：面板头部，含标题（点击也可开合历史）、历史、最小化、关闭 -->
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

        <!-- 区块：历史记录侧栏，覆盖在消息区左侧；支持新建、切换与删除会话 -->
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

        <!-- 区块：消息列表，用户消息右对齐、助手消息左对齐；加载中显示三点动画 -->
        <div v-show="!minified" class="ai-body" ref="bodyRef">
          <div v-for="(msg, i) in messages" :key="i" class="ai-msg" :class="msg.role">
            <div class="ai-bubble">
              <span v-if="msg.role === 'assistant' && msg.loading" class="ai-dots">
                <i></i><i></i><i></i>
              </span>
              <span v-else>{{ msg.content }}</span>
            </div>
          </div>
          <!-- 首屏欢迎语：仅当前会话只剩初始空助手消息时展示，避免与真实对话混排 -->
          <div v-if="messages.length === 1" class="ai-welcome">
            <p>👋 你好，我是小创助手！</p>
            <p>可以问我创新创业项目申报、审核、经费、比赛等问题～</p>
          </div>
        </div>

        <!-- 区块：输入区。Enter 直接发送，Shift+Enter 换行；输入为空或请求中时禁用发送 -->
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

    <!-- 区块：右下角悬浮按钮，未打开时显示"AI 助手"提示，打开后变为关闭图标 -->
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

/**
 * 单个会话结构。
 * messages 中的 role 取值：'user' 用户提问 / 'assistant' 助手回复；
 * loading 为前端临时标记（true 表示该条是等待回复的占位气泡），不写入后端。
 */
interface Conversation {
  /** 会话唯一 id，格式 c_时间戳_随机串 */
  id: string
  /** 会话标题，初始为「新对话」，首轮问答后由模型自动生成 */
  title: string
  /** 消息列表，首条通常是空的助手占位消息 */
  messages: (ChatMessage & { loading?: boolean })[]
  /** 创建时间戳，仅用于本地排序与展示 */
  createdAt: number
}

/** 本地持久化键名；带版本后缀，结构变更时可平滑升级而不读到脏数据 */
const STORAGE_KEY = 'ai_conversations_v1'

// ==================== 状态 ====================
/** 面板是否可见，由右下角悬浮按钮控制 */
const visible = ref(false)
/** 面板是否收起为标题栏（最小化） */
const minified = ref(false)
/** 是否展示历史会话侧栏 */
const showHistory = ref(false)
/** 是否正在等待 AI 回复；为真时禁用输入与发送，防止并发请求 */
const loading = ref(false)
/** 输入框内容 */
const input = ref('')
/** 消息滚动容器引用，用于新消息后自动滚到底部 */
const bodyRef = ref<HTMLElement>()

/** 全部会话列表，按创建时间倒序（新建的排在最前） */
const conversations = ref<Conversation[]>([])
/** 当前激活会话 id */
const currentId = ref<string>('')

// ==================== 计算属性 ====================
/** 当前激活的会话对象；id 失配时为 undefined，由调用方兜底 */
const currentConv = computed(() => conversations.value.find(c => c.id === currentId.value))
/** 当前会话的消息列表；无会话时返回空数组，模板可直接遍历 */
const messages = computed(() => currentConv.value?.messages ?? [])

// ==================== 本地持久化 ====================
/**
 * 从 localStorage 读取历史会话；无数据或解析失败时新建一个空会话。
 * 副作用：写入 conversations / currentId。
 * 注意：解析异常（旧版本数据结构损坏）时静默回退为空列表，不阻断组件初始化。
 */
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

/**
 * 把当前会话列表整体写回 localStorage。
 * 副作用：覆盖持久化数据；使用同步写入，数据量大时可能有轻微阻塞。
 */
function saveConversations() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations.value))
}

// ==================== 会话管理 ====================
/**
 * 新建会话并切换为当前会话。
 * @returns 新建的会话对象
 * 副作用：插入 conversations 头部、更新 currentId、立即持久化。
 * 说明：新会话预置一条空的助手消息，作为欢迎语的显示条件。
 */
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

/**
 * 历史侧栏「新建」：创建会话并收起侧栏，回到干净对话界面。
 */
function newConversation() {
  createConversation()
  showHistory.value = false
}

/**
 * 切换当前会话并收起侧栏。
 * @param id 目标会话 id
 * 副作用：更新 currentId、关闭历史侧栏、把消息区滚到底部。
 */
function switchConversation(id: string) {
  currentId.value = id
  showHistory.value = false
  scrollBottom()
}

/**
 * 删除指定会话（先二次确认）。
 * @param id 待删除会话 id
 * 副作用：弹出确认框；删除后若删的是当前会话，则切到第一个会话，全部删空时自动新建；
 *         最后持久化。用户取消确认时直接返回，不做任何修改。
 */
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

// ==================== 对话交互 ====================
/**
 * 切换面板显隐；打开时若处于最小化状态则自动还原，避免只看到一条标题栏。
 * 副作用：修改 visible / minified。
 */
function toggle() {
  visible.value = !visible.value
  if (visible.value && minified.value) minified.value = false
}

/**
 * 把消息区滚动到底部，展示最新一轮问答。
 * 副作用：在 nextTick 之后直接修改容器 scrollTop（依赖 DOM 已渲染完成）。
 */
function scrollBottom() {
  nextTick(() => {
    if (bodyRef.value) {
      bodyRef.value.scrollTop = bodyRef.value.scrollHeight
    }
  })
}

/**
 * 首轮对话后为会话生成短标题，便于历史侧栏辨认。
 * @param conv 当前会话
 * 副作用：请求 AI 接口（低温度 0.3）、成功后修改 title 并持久化。
 * 说明：仅当用户消息恰好 1 条且标题仍为「新对话」时执行；命名失败静默忽略，
 *       不弹出错误提示，避免干扰正常对话。
 */
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

/**
 * 发送当前输入并请求 AI 回复。
 * 流程：校验非空且不处于请求中 → 追加用户消息与助手 loading 占位 → 组装历史 →
 *       调用 aiChat → 用返回内容替换占位消息 → 持久化 → 尝试自动命名。
 * 副作用：修改输入框、消息列表、loading、localStorage；失败时展示错误消息。
 * 注意：请求历史会过滤 loading 占位与空内容，因为后端要求每条 content 至少 1 个字符。
 */
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

// ==================== 生命周期 ====================
/** 挂载时恢复本地历史会话，保证刷新页面后对话不丢 */
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

/* 悬浮按钮：固定在右下角，层级高于业务弹窗，避免被遮挡 */
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

/* 对话面板：浮于悬浮按钮上方，固定宽高，最小化时高度自适应标题栏 */
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
