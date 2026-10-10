<template>
  <el-dialog center v-model="dialogVisible" title="选择项目模板" width="900px" :close-on-click-modal="false">
    <div class="template-desc">
      <el-alert type="info" :closable="false" show-icon>
        选择一个模板预填申报信息，所有内容可在后续步骤中自由修改。也可以选择"空白创建"从零开始。
      </el-alert>
    </div>

    <div class="template-grid">
      <el-card
        v-for="tpl in templates"
        :key="tpl.id"
        shadow="hover"
        class="template-card"
        :class="{ active: selectedId === tpl.id }"
      >
        <template #header>
          <div class="card-header">
            <span class="card-title">{{ tpl.name }}</span>
            <el-tag size="small">{{ tpl.category_name }}</el-tag>
          </div>
        </template>

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

        <p class="card-desc">{{ tpl.description }}</p>

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

        <div class="card-footer">
          <el-button type="primary" @click="handleSelect(tpl)">使用此模板</el-button>
        </div>
      </el-card>
    </div>

    <template #footer>
      <el-button @click="handleSkip">跳过，使用空白创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { projectTemplates, type ProjectTemplate } from '@/data/projectTemplates'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
  }>(),
  { modelValue: false }
)
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  select: [template: ProjectTemplate]
  skip: []
}>()

const templates = projectTemplates
const selectedId = ref<string | null>(null)

const dialogVisible = ref(props.modelValue)
watch(
  () => props.modelValue,
  (val) => {
    dialogVisible.value = val
  }
)
watch(dialogVisible, (val) => {
  emit('update:modelValue', val)
})

function handleSelect(tpl: ProjectTemplate) {
  selectedId.value = tpl.id
  emit('select', tpl)
  dialogVisible.value = false
}

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
