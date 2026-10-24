<!--
  ==== 403 无权限 ====
  解决的问题：用户已登录但访问了当前角色无权进入的页面时，给出明确反馈而不是空白页或死循环。
  对应角色与路由：全部角色通用，路由 /403；由路由守卫在角色不匹配时跳转而来。
  依赖 API：无，纯静态提示页。
  关键交互流程：展示无权限文案 -> 点击「返回首页」回到登录后的默认工作台。
-->
<template>
  <!-- 区块：无权限结果页，保留返回首页的唯一出口，避免用户困在错误页 -->
  <el-result icon="warning" title="403" sub-title="抱歉，您没有权限访问此页面">
    <template #extra>
      <el-button type="primary" @click="router.push('/')">返回首页</el-button>
    </template>
  </el-result>
</template>

<script setup lang="ts">
// ==================== 路由 ====================
import { useRouter } from 'vue-router'
/** 路由实例：用于返回首页；首页会再按当前登录角色渲染可访问菜单 */
const router = useRouter()
</script>
