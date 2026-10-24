<!--
  项目切换器（ProjectSwitcher）
  面向角色：中期检查 / 成果登记 / 结项验收等单项目子页面的访问者。
  核心功能：加载当前用户可访问、且处于当前页面阶段的项目，供用户直接切换，
           避免为了看另一个项目而反复返回列表页。
  调用 API：getProjectList（拉取项目列表，page_size=200 后在本地按状态过滤）。
  关键状态约束：
    - 中期检查、成果登记允许 [6 已立项, 7 中期检查中, 8 待结项, 9 已结题]，
      包含只读回看，历史项目仍可查阅；
    - 结项验收只允许 [8 待结项, 9 已结题]；
    - 当前项目不在可选集合时，下拉框显示占位文案而不是非法 ID。
  特别注意：切换前会先移除当前路由的标签页，再 push 新地址，
           防止每切换一次项目就多出一个页签。
-->
<template>
  <!-- 可搜索下拉：项目较多时按名称快速定位；model-value 只读，实际跳转由 change 处理 -->
  <el-select
    :model-value="selectValue"
    class="project-switcher"
    filterable
    placeholder="切换项目"
    @change="onChange"
  >
    <!-- 选项值统一转数字，与 currentId 类型对齐，避免严格比较失败 -->
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

// ==================== Props 与依赖 ====================

const props = defineProps<{
  /** 当前页面所属项目 ID，用于判断下拉选中项 */
  currentId: number
  /** 当前阶段标识，决定可切换项目的状态范围与跳转路径 */
  suffix: 'midterm' | 'achievements' | 'final'
}>()

/** 各页面可切换的项目状态：含只读回看（中期通过后 / 已结题） */
const STATUS_BY_SUFFIX: Record<'midterm' | 'achievements' | 'final', number[]> = {
  midterm: [6, 7, 8, 9],
  achievements: [6, 7, 8, 9],
  final: [8, 9],
}

const route = useRoute()
const router = useRouter()
const tagsStore = useTagsStore()

/** 过滤后的可切换项目列表，仅当前阶段允许的状态会进入下拉选项 */
const list = ref<any[]>([])

// ==================== 选中值 ====================

/** 当前项目不属于本阶段时，下拉显示占位文案而非不在选项中的 ID */
const selectValue = computed(() =>
  list.value.some((p) => Number(p.id) === props.currentId) ? props.currentId : undefined
)

// ==================== 数据加载 ====================

/**
 * 拉取项目列表并按当前阶段过滤。
 * 说明：接口未提供按阶段批量过滤的参数，因此一次取 200 条后在本地过滤；
 *       上限存在的意义是防止列表接口被无限放大，超出部分不会出现在下拉中。
 * 失败处理：异常由全局请求拦截器提示，本函数不额外捕获，列表保持为空。
 */
async function load() {
  const res = await getProjectList({ page: 1, page_size: 200 } as any)
  const allowed = STATUS_BY_SUFFIX[props.suffix] || []
  list.value = (res.data.items || []).filter((p: any) => allowed.includes(Number(p.status)))
}

// ==================== 切换交互 ====================

/**
 * 切换项目：先清理旧标签页再跳转。
 * 失败处理：选择当前项目时直接返回，避免重复导航。
 * 副作用：修改 tagsStore 中的页签集合，并触发路由跳转。
 * @param id 目标项目 ID
 */
function onChange(id: number) {
  if (id === props.currentId) return
  // 复用当前标签页：先移除旧项目的标签，避免每切换一次项目就新增一个标签
  tagsStore.removeView(route.path)
  router.push(`/projects/${id}/${props.suffix}`)
}

// ==================== 生命周期 ====================

// 仅首次挂载拉取一次；阶段由 props.suffix 决定，同页内不会变化，无需监听
onMounted(load)
</script>

<style scoped>
.project-switcher {
  width: 200px;
}
</style>