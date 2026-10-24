<!--
  ==== ReviewTemplatePicker ====
  职责：评语模板选择器，内置「通过 / 驳回 / 通用」三类评审意见模板，
        点击某个模板即把整段文案交给父组件回填到评审意见输入框。
  复用：学院初审、校级复审、专家评审等需要填写评审意见 / 驳回理由的弹窗与抽屉。
  契约：props：无，模板数据来自本地 @/data/reviewTemplates；
        emits：select(text)（选中模板的完整文案，父组件通常直接写入表单字段）；
        无插槽。
  注意：1) 对话框 append-to-body 且 z-index 抬高到 4000，保证浮在业务弹窗之上；
        2) 选中模板后立即关闭弹窗，但不会自动提交评审；
        3) 模板只是默认措辞，调用方应允许教师继续编辑再提交。
-->
<template>
  <!-- 区块：触发入口，通常放在评语输入框旁边的工具栏位置 -->
  <el-button link type="primary" size="small" @click="dialogVisible = true">📝 插入评语模板</el-button>
  <!-- 区块：模板选择弹窗，按通过/驳回/通用分页签展示 -->
  <el-dialog
    v-model="dialogVisible"
    title="选择评语模板"
    width="520px"
    center
    :close-on-click-modal="true"
    append-to-body
    :z-index="4000"
    class="template-picker-dialog"
  >
    <el-tabs v-model="activeTab">
      <!-- 通过类模板：适用于同意立项、中期通过、同意结题等正向结论 -->
      <el-tab-pane label="通过模板" name="pass">
        <div class="template-list">
          <div
            v-for="t in passTemplates"
            :key="t.label"
            class="template-item"
            @click="handleSelect(t.text)"
          >
            <span class="template-label">{{ t.label }}</span>
            <span class="template-text">{{ t.text }}</span>
          </div>
        </div>
      </el-tab-pane>
      <!-- 驳回类模板：强调指出具体问题与修改方向，状态 10 驳回时使用 -->
      <el-tab-pane label="驳回模板" name="reject">
        <div class="template-list">
          <div
            v-for="t in rejectTemplates"
            :key="t.label"
            class="template-item"
            @click="handleSelect(t.text)"
          >
            <span class="template-label">{{ t.label }}</span>
            <span class="template-text">{{ t.text }}</span>
          </div>
        </div>
      </el-tab-pane>
      <!-- 通用模板：不含明确通过/驳回倾向的中性表述，数据为空时显示提示 -->
      <el-tab-pane label="通用" name="common">
        <div class="template-list">
          <div
            v-for="t in commonTemplates"
            :key="t.label"
            class="template-item"
            @click="handleSelect(t.text)"
          >
            <span class="template-label">{{ t.label }}</span>
            <span class="template-text">{{ t.text }}</span>
          </div>
          <div v-if="commonTemplates.length === 0" class="empty-tip">暂无通用模板</div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { reviewTemplates } from '@/data/reviewTemplates'

// ==================== emits ====================
/**
 * 选中模板事件：载荷为模板的完整文案。
 * 父组件一般直接拼接/覆盖到评审意见字段，关闭弹窗与后续提交由父组件负责。
 */
const emit = defineEmits<{
  select: [text: string]
}>()

// ==================== 状态 ====================
/** 模板弹窗可见性，由触发按钮打开、选中模板或点击遮罩关闭 */
const dialogVisible = ref(false)
/** 当前页签：pass 通过 / reject 驳回 / common 通用，默认停在通过类 */
const activeTab = ref<'pass' | 'reject' | 'common'>('pass')

// ==================== 计算属性 ====================
/** 通过类模板列表，从本地模板库按 category 过滤 */
const passTemplates = computed(() => reviewTemplates.filter((t) => t.category === 'pass'))
/** 驳回类模板列表 */
const rejectTemplates = computed(() => reviewTemplates.filter((t) => t.category === 'reject'))
/** 通用模板列表，可能为空，模板中已做空态提示 */
const commonTemplates = computed(() => reviewTemplates.filter((t) => t.category === 'common'))

// ==================== 事件处理 ====================
/**
 * 选中某个模板：向外抛出文案并关闭弹窗。
 * @param text 模板正文
 * 副作用：触发 select 事件、修改 dialogVisible。
 */
function handleSelect(text: string) {
  emit('select', text)
  dialogVisible.value = false
}
</script>

<style>
/*
  评语模板对话框通过 append-to-body 挂载到 body 下，
  scoped 样式无法命中，必须使用全局样式才能保证垂直居中
*/
/* 全局块：选择器限定 .template-picker-dialog 前缀，避免影响其他 el-dialog */
.template-picker-dialog.el-dialog {
  top: 50% !important;
  margin-top: 0 !important;
  transform: translateY(-50%);
}
</style>

<style scoped>
/* 模板列表：限高滚动，模板再多也不会把弹窗撑出视口 */
.template-list {
  max-height: 360px;
  overflow-y: auto;
}
.template-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s;
  margin-bottom: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.template-item:hover {
  background-color: var(--el-color-primary-light-9);
}
.template-label {
  font-size: 12px;
  color: var(--el-color-primary);
  font-weight: 500;
}
.template-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}
.empty-tip {
  text-align: center;
  color: #909399;
  padding: 20px 0;
  font-size: 13px;
}
</style>
