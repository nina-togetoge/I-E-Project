export interface ProjectBudgetItem {
  budget_item: string
  budget_amount: number
  remark?: string
}

export interface ProjectTemplate {
  id: string
  name: string
  category: number
  category_name: string
  level: number
  level_name: string
  summary: string
  innovation_points: string
  expected_results: string
  budgets: ProjectBudgetItem[]
  description: string
  tags: string[]
}

export const projectTemplates: ProjectTemplate[] = [
  {
    id: 'dachuang',
    name: '国家级大学生创新创业训练计划模板',
    category: 1,
    category_name: '创新训练',
    level: 3,
    level_name: '省部级',
    summary:
      '本项目围绕XX领域核心问题，采用XX技术手段，旨在研发具有创新性的XX系统/方法。项目基于现有研究基础，结合前沿理论，预期在XX方面取得突破，为XX行业发展提供技术支撑与实践范例。',
    innovation_points:
      '<p>1. <b>技术创新</b>：首次将XX算法与XX模型相结合，显著提升了XX任务的精度与效率，较现有方案性能提升XX%以上。</p>' +
      '<p>2. <b>方法创新</b>：提出了一种全新的XX框架，通过XX机制实现了XX能力的有效整合，解决了传统方法中XX难以兼顾的问题。</p>' +
      '<p>3. <b>应用创新</b>：将研究成果落地于XX实际场景，构建了XX原型系统，经测试验证可满足XX场景的实际需求，具有良好的产业化推广前景。</p>',
    expected_results:
      '<p>1. <b>学术成果</b>：发表SCI/EI检索论文1-2篇，申请发明专利1项。</p>' +
      '<p>2. <b>知识产权</b>：申请软件著作权1-2项，形成技术文档1套。</p>' +
      '<p>3. <b>系统原型</b>：完成可演示的原型系统1套，包含XX核心功能模块，通过用户验收测试。</p>' +
      '<p>4. <b>竞赛获奖</b>：争取在XX创新创业赛事中获得省部级以上奖项。</p>',
    budgets: [
      { budget_item: '材料费', budget_amount: 5000, remark: '实验耗材、元器件采购' },
      { budget_item: '差旅费', budget_amount: 3000, remark: '调研、参加学术会议差旅' },
      { budget_item: '劳务费', budget_amount: 4000, remark: '学生助研劳务补贴' },
    ],
    description: '适用于国家级、省部级大创项目申报，涵盖创新训练类项目完整申报结构。',
    tags: ['大创', '创新训练', '国家级', '省部级'],
  },
  {
    id: 'tiaozhanbei',
    name: '挑战杯创业计划竞赛模板',
    category: 3,
    category_name: '创业实践',
    level: 2,
    level_name: '校级',
    summary:
      'XX科技有限公司（筹）是一家专注于XX领域的创新型企业，依托自主研发的XX核心技术，为XX客户群体提供XX产品/服务。公司采用XX商业模式，通过XX渠道触达用户，力争在3年内成为XX细分市场的领军企业。',
    innovation_points:
      '<p>1. <b>产品创新</b>：独创XX产品形态，集成XX核心功能，相比市场同类产品具备XX、XX、XX三大差异化优势，用户体验显著提升。</p>' +
      '<p>2. <b>技术壁垒</b>：核心团队拥有XX项原创技术，已申请专利XX项，技术门槛高，竞争对手短期难以复制。</p>' +
      '<p>3. <b>商业模式创新</b>：采用XX+XX的双轮驱动模式，既保证了初期现金流健康，又具备长期规模化增长潜力，市场空间达XX亿元。</p>',
    expected_results:
      '<p>1. <b>商业计划</b>：完成完整的创业计划书1份，包含市场分析、产品方案、运营策略、财务预测等模块。</p>' +
      '<p>2. <b>原型产品</b>：完成MVP最小可行产品开发，获得首批XX名种子用户验证。</p>' +
      '<p>3. <b>竞赛目标</b>：冲击挑战杯省赛金奖，争取进入国赛。</p>' +
      '<p>4. <b>创业落地</b>：赛后注册成立公司，对接天使轮融资，启动正式商业化运营。</p>',
    budgets: [
      { budget_item: '材料费', budget_amount: 3000, remark: '产品原型制作、样品打样' },
      { budget_item: '差旅费', budget_amount: 4000, remark: '市场调研、用户访谈差旅' },
      { budget_item: '劳务费', budget_amount: 5000, remark: '核心团队劳务与激励' },
    ],
    description: '适用于挑战杯、创青春等创业计划类竞赛申报。',
    tags: ['挑战杯', '创业计划', '商业计划书', '创业实践'],
  },
  {
    id: 'hulianwangjia',
    name: '互联网+大学生创新创业大赛模板',
    category: 2,
    category_name: '创业训练',
    level: 2,
    level_name: '校级',
    summary:
      '项目聚焦XX行业痛点，以互联网+XX技术为核心驱动力，打造国内领先的XX平台。通过整合XX资源，链接XX供需双方，构建XX生态闭环，解决行业长期存在的XX、XX、XX三大痛点问题，预计3年内覆盖XX万用户，实现年营收XX万元。',
    innovation_points:
      '<p>1. <b>模式创新</b>：首创XX互联网平台模式，通过XX机制实现双边市场的快速冷启动，网络效应显著。</p>' +
      '<p>2. <b>技术驱动</b>：运用AI大数据算法，实现XX智能匹配，匹配效率提升XX%，用户满意度达XX%以上。</p>' +
      '<p>3. <b>社会价值</b>：项目具有显著的社会效益，可带动XX人就业/助力XX产业升级/服务XX群体，契合国家XX战略方向。</p>',
    expected_results:
      '<p>1. <b>平台开发</b>：完成微信小程序+H5+PC端多端平台开发，上线运营。</p>' +
      '<p>2. <b>用户增长</b>：6个月内实现注册用户XX人，月活用户XX人，付费转化率XX%。</p>' +
      '<p>3. <b>赛事成绩</b>：冲击互联网+省赛金奖，力争国赛奖牌。</p>' +
      '<p>4. <b>收入验证</b>：完成XX万元营收验证，实现正向现金流。</p>',
    budgets: [
      { budget_item: '材料费', budget_amount: 4000, remark: '服务器、云服务、域名采购' },
      { budget_item: '差旅费', budget_amount: 3500, remark: '行业调研、供应链对接' },
      { budget_item: '劳务费', budget_amount: 4500, remark: '开发运营团队劳务补贴' },
    ],
    description: '适用于互联网+大赛高教主赛道、青年红色筑梦之旅赛道申报。',
    tags: ['互联网+', '创新创业', '平台型项目', '商业落地'],
  },
]
