<!--
  ==== StatusTag ====
  职责：项目状态标签，把后端数字状态码映射为中文文案与 el-tag 配色。
  复用：项目列表、项目详情、审核工作台、我的项目、专家评审列表等所有需要展示项目状态的页面。
  契约：props：status（项目状态码，必填）、label（覆盖文案）、overrideType（覆盖颜色）；
        无 emit、无插槽。
  注意：1) 状态 2 / 4 是「瞬时」状态，表示初审 / 复审通过后立即流转，界面上通常一闪而过；
        2) 状态 10「已驳回」在不同业务场景文案不同（可修改重提 / 已落选），
           由父组件通过 label 覆盖；
        3) 未识别的状态码兜底显示「未知(n)」并使用 info 色，便于发现后端新增状态。
-->
<template>
  <!-- 区块：状态标签本体，颜色与文案全部由映射表派生，组件自身不含业务判断 -->
  <el-tag :type="tagType" size="small">{{ statusText }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

// ==================== props ====================
/** 状态标签入参；唯一必填项是后端项目状态码。 */
const props = defineProps<{
  /** 项目状态码，取值见 statusMap，必填 */
  status: number
  /** 可选：覆盖状态文案（如状态 10 区分「已驳回（可修改重提）」与「已落选」） */
  label?: string
  /** 可选：覆盖标签颜色，用于少数需要特殊配色的业务场景 */
  overrideType?: string
}>()

// ==================== 状态映射 ====================
/**
 * 项目状态码 → 文案 + 标签色。
 * 0 草稿（学生编辑中）；12 待指导教师确认；1 待学院初审；
 * 2 学院初审通过（瞬时）；3 待校级复审；4 校级复审通过（瞬时）；
 * 5 待专家评审；13 待分配评审专家；6 已立项；7 中期检查中；
 * 8 待结题；9 已结题；10 已驳回；11 已撤销。
 */
const statusMap: Record<number, { text: string; type: string }> = {
  0: { text: '草稿', type: 'info' }, // 学生保存未提交
  12: { text: '待指导教师确认', type: 'warning' }, // 提交后由指导教师先行确认
  1: { text: '待学院初审', type: 'warning' }, // 指导教师确认后进入学院初审
  2: { text: '学院初审通过', type: 'success' }, // 瞬时状态，随即流转至校级
  3: { text: '待校级复审', type: 'warning' }, // 教务处/校级管理员复审
  4: { text: '校级复审通过', type: 'success' }, // 瞬时状态，随即进入专家评审
  5: { text: '待专家评审', type: 'warning' }, // 已分配专家或等待专家打分
  13: { text: '待分配评审专家', type: 'warning' }, // 管理员尚未指派评审专家
  6: { text: '已立项', type: 'primary' }, // 立项成功，进入项目执行期
  7: { text: '中期检查中', type: 'warning' }, // 需提交中期检查材料
  8: { text: '待结题', type: 'warning' }, // 中期通过，等待结题材料
  9: { text: '已结题', type: 'success' }, // 项目完成并归档
  10: { text: '已驳回', type: 'danger' }, // 任一审核环节驳回，可配合 label 区分场景
  11: { text: '已撤销', type: 'info' }, // 学生主动撤回申报
}

// ==================== 计算属性 ====================
/**
 * 最终展示文案：优先使用父组件覆盖值，其次查映射表，最后兜底为「未知(状态码)」。
 * 兜底文案便于在前端快速发现后端新增了未适配的状态。
 */
const statusText = computed(() => props.label || statusMap[props.status]?.text || `未知(${props.status})`)

/**
 * 最终标签颜色：优先使用 overrideType，其次查映射表，兜底 info。
 * 返回值直接作为 el-tag 的 type 使用。
 */
const tagType = computed(() => props.overrideType || statusMap[props.status]?.type || 'info')
</script>