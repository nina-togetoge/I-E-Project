# ====================================================================
# API 路由包初始化
# ----------------------------------------------------------------------------
# 本包按业务域拆分路由模块，统一由上层 app.api 注册并挂载到 /api 前缀下。
# 模块分工与前端对应关系：
#   user_router.py          /auth、/users、/colleges、/logs
#                           登录注册、用户管理、学院管理、操作日志（系统管理端）
#   project_router.py       /projects、/achievements、/statistics
#                           项目申报全流程、成果登记认定、数据统计（项目端/管理端）
#   review_router.py        /reviews、/midterm、/changes
#                           审核待办、专家评审、中期检查、变更/延期（审核端）
#   expense_router.py       /expenses
#                           经费报销申请与导师/学院/财务三级审批（经费端）
#   certificate_router.py   /certificates
#                           学生「我的获奖证书」（个人中心）
#   competition_router.py   /competitions
#                           大赛信息维护与校级比赛获奖名单生成（管理端）
#   notification_router.py  /notifications
#                           站内通知消息中心（顶栏铃铛）
#   announcement_router.py  /announcements
#                           系统公告发布与浏览（首页/管理端）
#   common_router.py        /files、/excel、/common、/health
#                           附件上传下载、Excel 导入导出、字典、健康检查
#   ai_router.py            /ai
#                           智能助手对话（右下角 AI 入口）
# 说明：本文件只承担包标识作用，不在此处导入子模块，避免路由之间产生循环依赖；
#       各子路由的挂载顺序与鉴权由 app.api 层显式控制。
# ====================================================================
