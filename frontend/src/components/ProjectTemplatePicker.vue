<!--
  ==== ProjectTemplatePicker ====
  职责：项目申报模板选择弹窗，以卡片形式展示模板的分类、级别、标签、简介与预设预算项；
        选定后把模板对象交给申报流程预填，也支持跳过模板从空白开始。
  复用：学生端「新建项目 / 发起申报」流程的第一步。
  契约：props：modelValue（v-model 控制弹窗显隐，默认 false）；
        emits：update:modelValue（显隐同步）、select(template)（选中模板对象，载荷为 ProjectTemplate）、
               skip()（跳过模板，父组件按空白草稿创建）；
        无插槽。
  注意：1) 模板来自前端静态数据 @/data/projectTemplates，其中预算项仅用于预填草稿；
        2) 选中或跳过都会关闭弹窗，具体字段预填由父组件负责；
        3) 级别颜色按 level 简化着色（3 及以上用 danger、2 用 warning、其余 info），
           展示文案以 level_name 为准。
-->
<template>
  <!-- 区块：模板选择弹窗，禁止点击遮罩关闭，避免误触丢失选择流程 -->
  <el-dialog center v-model="dialogVisible" title="选择项目模板" width="900px" :close-on-click-modal="false">
    <!-- 区块：说明提示，明确"模板可改、也可空白创建"，降低学生选择压力 -->
    <div class="template-desc">
      <el-alert type="info" :closable="false" show-icon>
        选择一个模板预填申报信息，所有内容可在后续步骤中自由修改。也可以选择"空白创建"从零开始。
      </el-alert>
    </div>

    <!-- 区块：模板卡片网格，宽屏 3 列、窄屏降为 1 列；选中卡片有主色描边 -->
    <div class="template-grid">
      <el-card
        v-for="tpl in templates"
        :key="tpl.id"
        shadow="hover"
        class="template-card"
        :class="{ active: selectedId === tpl.id }"
      >
        <!-- 卡片头：模板名称 + 所属分类（创新训练 / 创业训练 / 创业实践） -->
        <template #header>
          <div class="card-header">
            <span class="card-title">{{ tpl.name }}</span>
            <el-tag size="small">{{ tpl.category_name }}</el-tag>
          </div>
        </template>

        <!-- 标签：模板适用的方向关键词，便于学生快速筛选 -->
        <div class="card-tags">
          <el-tag
            v-for="tag in tpl.tags"
            :key="tag"
            size="small"
            type="info"
            effect="plain"
            style="margin-right: 6px; margin-bottom: 6px;"
          >
            {{ tag }}
          </el-tag>
        </div>

        <!-- 简介：说明模板适用场景与预期填写方式 -->
        <p class="card-desc">{{ tpl.description }}</p>

        <!-- 元信息：适用级别与预设预算项数量/合计，帮助判断模板是否匹配项目规模 -->
        <div class="card-meta">
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="适用级别">
              <el-tag size="small" :type="tpl.level === 3 ? 'danger' : tpl.level === 2 ? 'warning' : 'info'">
                {{ tpl.level_name }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="预设预算项">
              {{ tpl.budgets.length }} 项（合计 ¥{{ tpl.budgets.reduce((s, b) => s + Number(b.budget_amount || 0), 0).toFixed(2) }}）
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 卡片操作：选中该模板并关闭弹窗 -->
        <div class="card-footer">
          <el-button type="primary" @click="handleSelect(tpl)">使用此模板</el-button>
        </div>
      </el-card>
    </div>

    <!-- 区块：弹窗底部，提供"不使用模板"的出口，保证流程可继续 -->
    <template #footer>
      <el-button @click="handleSkip">跳过，使用空白创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { projectTemplates, type ProjectTemplate } from '@/data/projectTemplates'

// ==================== props / emits ====================
/** 显隐控制：使用 v-model，父组件自行决定何时弹出模板选择。 */
const props = withDefaults(
  defineProps<{
    /** 弹窗是否可见，默认 false */
    modelValue: boolean
  }>(),
  { modelValue: false }
)
/**
 * 对外事件：
 * - update:modelValue：显隐同步，配合 v-model 使用；
 * - select：选中模板，载荷为完整模板对象，父组件据此预填摘要/创新点/预期成果/预算；
 * - skip：选择空白创建，父组件应创建空草稿而不套用任何模板。
 */
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  select: [template: ProjectTemplate]
  skip: []
}>()

// ==================== 状态 ====================
/** 模板数据源（前端静态定义，不在运行时请求后端） */
const templates = projectTemplates
/** 当前选中的模板 id，用于卡片高亮；未选择时为 null */
const selectedId = ref<string | null>(null)

/** 内部显隐副本：与 modelValue 双向同步，避免直接改 props */
const dialogVisible = ref(props.modelValue)
/** 外部 v-model 变化 → 同步到内部副本（父组件主动打开/关闭时生效） */
watch(
  () => props.modelValue,
  (val) => {
    dialogVisible.value = val
  }
)
/** 内部关闭（选中/跳过/点遮罩）→ 回写 v-model，保证父子状态一致 */
watch(dialogVisible, (val) => {
  emit('update:modelValue', val)
})

// ==================== 事件处理 ====================
/**
 * 使用指定模板：记录选中态、抛出模板对象并关闭弹窗。
 * @param tpl 被选中的模板
 * 副作用：修改 selectedId / dialogVisible，触发 select 与 update:modelValue。
 */
function handleSelect(tpl: ProjectTemplate) {
  selectedId.value = tpl.id
  emit('select', tpl)
  dialogVisible.value = false
}

/**
 * 跳过模板：抛出 skip 事件并关闭弹窗，由父组件创建空白草稿。
 * 副作用：修改 dialogVisible，触发 skip 与 update:modelValue。
 */
function handleSkip() {
  emit('skip')
  dialogVisible.value = false
}
</script>

<style scoped>
.template-desc {
  margin-bottom: 20px;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.template-card {
  display: flex;
  flex-direction: column;
  transition: all 0.2s;
  cursor: pointer;
}

.template-card:hover {
  transform: translateY(-2px);
}

.template-card.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-weight: 600;
  font-size: 15px;
}

.card-tags {
  margin-bottom: 12px;
}

.card-desc {
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
  min-height: 60px;
  margin-bottom: 12px;
}

.card-meta {
  margin-bottom: 16px;
  flex: 1;
}

.card-footer {
  text-align: center;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}

@media (max-width: 900px) {
  .template-grid {
    grid-template-columns: 1fr;
  }
}
</style>
