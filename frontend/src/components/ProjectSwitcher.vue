<!--
  项目切换器（用于中期检查 / 成果登记 / 结项验收等单项目子页面）
  加载当前用户可访问的全部项目，切换后跳转到对应子页面，避免被锁定在单个项目。
-->
<template>
  <el-select
    :model-value="currentId"
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
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getProjectList } from '@/api/project'

const props = defineProps<{
  currentId: number
  suffix: 'midterm' | 'achievements' | 'final'
}>()

const router = useRouter()
const list = ref<any[]>([])

async function load() {
  const res = await getProjectList({ page: 1, page_size: 200 } as any)
  list.value = res.data.items || []
}

function onChange(id: number) {
  if (id === props.currentId) return
  router.push(`/projects/${id}/${props.suffix}`)
}

onMounted(load)
</script>

<style scoped>
.project-switcher {
  width: 200px;
}
</style>