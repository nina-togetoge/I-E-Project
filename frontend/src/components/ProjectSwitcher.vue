<!--
  项目切换器（用于中期检查 / 成果登记 / 结项验收等单项目子页面）
  加载当前用户可访问、且处于当前页面阶段的项目，切换后跳转到对应子页面，避免被锁定在单个项目。
-->
<template>
  <el-select
    :model-value="selectValue"
    class="project-switcher"
    filterable
    placeholder="切换项目"
    @change="onChange"
  >
    <el-option
      v-for="p in list"
      :key="p.id"
      :label="p.project_name"
      :value="Number(p.id)"
    />
  </el-select>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getProjectList } from '@/api/project'
import { useTagsStore } from '@/store/tags'

const props = defineProps<{
  currentId: number
  suffix: 'midterm' | 'achievements' | 'final'
}>()

/** 各页面可切换的项目状态：中期检查中 / 已立项及之后 / 待结题 */
const STATUS_BY_SUFFIX: Record<'midterm' | 'achievements' | 'final', number[]> = {
  midterm: [7],
  achievements: [6, 7, 8, 9],
  final: [8],
}

const route = useRoute()
const router = useRouter()
const tagsStore = useTagsStore()
const list = ref<any[]>([])

/** 当前项目不属于本阶段时，下拉显示占位文案而非不在选项中的 ID */
const selectValue = computed(() =>
  list.value.some((p) => Number(p.id) === props.currentId) ? props.currentId : undefined
)

async function load() {
  const res = await getProjectList({ page: 1, page_size: 200 } as any)
  const allowed = STATUS_BY_SUFFIX[props.suffix] || []
  list.value = (res.data.items || []).filter((p: any) => allowed.includes(Number(p.status)))
}

function onChange(id: number) {
  if (id === props.currentId) return
  // 复用当前标签页：先移除旧项目的标签，避免每切换一次项目就新增一个标签
  tagsStore.removeView(route.path)
  router.push(`/projects/${id}/${props.suffix}`)
}

onMounted(load)
</script>

<style scoped>
.project-switcher {
  width: 200px;
}
</style>