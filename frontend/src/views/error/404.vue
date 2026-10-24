<!--
  ==== 404 页面不存在 ====
  解决的问题：用户输入错误地址或访问已下线的旧链接时，给出统一兜底页，避免白屏。
  对应角色与路由：全部角色通用，路由 /404；路由表中以 /:pathMatch(.*)* 通配重定向到此页。
  依赖 API：无，纯静态提示页。
  关键交互流程：展示不存在文案 -> 点击「返回首页」回到登录后的默认工作台。
-->
<template>
  <!-- 区块：页面不存在结果页，提供返回首页入口 -->
  <el-result icon="info" title="404" sub-title="抱歉，您访问的页面不存在">
    <template #extra>
      <el-button type="primary" @click="router.push('/')">返回首页</el-button>
    </template>
  </el-result>
</template>

<script setup lang="ts">
// ==================== 路由 ====================
import { useRouter } from 'vue-router'
/** 路由实例：用于返回首页，回到按角色渲染的正常入口 */
const router = useRouter()
</script>
