/**
 * 项目申报模板静态配置
 *
 * 模块职责：
 *  - 为“新建项目”页提供一键套用的申报书骨架，覆盖大创、挑战杯、互联网+ 三类常见赛事。
 *  - 表单页读取模板后把 summary / innovation_points / expected_results 等字段填充到对应富文本编辑器，
 *    预算列表直接映射到经费明细表格；用户可在此基础上修改后提交。
 *
 * 使用方：ProjectCreate 页面（模板选择卡片）、需要预填申报内容的表单组件。
 * 关键约定：
 *  - id 为前端唯一标识，仅用于选中态与埋点，不是后端数据库主键；
 *  - category / level 使用数字编码，category_name / level_name 是展示文案，两者需同步维护；
 *  - summary、innovation_points、expected_results 为 HTML 片段，填充后需经 richText 安全渲染。
 */

/** 预算明细项：与项目经费表的字段命名保持一致，便于直接映射提交 */
export interface ProjectBudgetItem {
  /** 预算科目名称，如材料费、差旅费、劳务费 */
  budget_item: string
  /** 预算金额（元） */
  budget_amount: number
  /** 科目说明，解释该笔经费的用途 */
  remark?: string
}

/** 单个项目申报模板的结构 */
export interface ProjectTemplate {
  /** 模板唯一标识（前端用） */
  id: string
  /** 模板名称，展示在模板选择卡片上 */
  name: string
  /** 项目类别编码，1 创新训练 / 2 创业训练 / 3 创业实践 */
  category: number
  /** 项目类别展示名，与 category 对应 */
  category_name: string
  /** 项目级别编码，模板中按 2 校级、4 国家级配置 */
  level: number
  /** 项目级别展示名，与 level 对应 */
  level_name: string
  /** 项目简介（HTML），预填到申报书“项目简介”栏 */
  summary: string
  /** 创新点（HTML），预填到“项目创新点”栏 */
  innovation_points: string
  /** 预期成果（HTML），预填到“预期成果”栏 */
  expected_results: string
  /** 预算明细列表，预填到经费预算表格 */
  budgets: ProjectBudgetItem[]
  /** 模板适用场景说明，帮助用户选择 */
  description: string
  /** 检索标签，用于模板筛选与搜索 */
  tags: string[]
}

/**
 * 内置项目模板列表，按赛事场景划分。
 * 所有正文均为占位式示例（含 XX），目的是给出结构而非可直接提交的内容。
 */
export const projectTemplates: ProjectTemplate[] = [
  // 大创模板：创新训练类，正文按“研究背景 + 创新点 + 成果 + 预算”组织
  // 适合以技术研发、论文专利为主要产出的小组
  // 预算按材料费/差旅费/劳务费三项示例，可按实际科目增删
  {
    id: 'dachuang',
    name: '国家级大学生创新创业训练计划模板',
    category: 1,
    category_name: '创新训练',
    level: 4,
    level_name: '国家级',
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
      '<p>4. <b>竞赛获奖</b>：争取在XX创新创业赛事中获得省级以上奖项。</p>',
    // 示例预算：材料、差旅、劳务三类，合计 1.2 万元，可按项目实际调整
    budgets: [
      { budget_item: '材料费', budget_amount: 5000, remark: '实验耗材、元器件采购' },
      { budget_item: '差旅费', budget_amount: 3000, remark: '调研、参加学术会议差旅' },
      { budget_item: '劳务费', budget_amount: 4000, remark: '学生助研劳务补贴' },
    ],
    description: '适用于国家级、省级大创项目申报，涵盖创新训练类项目完整申报结构。',
    tags: ['大创', '创新训练', '国家级', '省级'],
  },
  // 挑战杯偏向创业计划，正文按“公司介绍 + 商业模式 + 竞赛目标”组织
  // 预算侧重原型制作与市场调研，适合已有初步产品形态的团队
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
    // 创业类预算：更侧重原型制作、市场调研与核心团队激励
    budgets: [
      { budget_item: '材料费', budget_amount: 3000, remark: '产品原型制作、样品打样' },
      { budget_item: '差旅费', budget_amount: 4000, remark: '市场调研、用户访谈差旅' },
      { budget_item: '劳务费', budget_amount: 5000, remark: '核心团队劳务与激励' },
    ],
    description: '适用于挑战杯、创青春等创业计划类竞赛申报。',
    tags: ['挑战杯', '创业计划', '商业计划书', '创业实践'],
  },
  // 互联网+ 模板强调平台模式、技术驱动与社会价值，预算包含云服务采购
  // 适合平台型、可快速验证用户增长与商业闭环的项目
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
    // 平台型项目预算：材料费实际用于服务器/云服务/域名等基础设施
    budgets: [
      { budget_item: '材料费', budget_amount: 4000, remark: '服务器、云服务、域名采购' },
      { budget_item: '差旅费', budget_amount: 3500, remark: '行业调研、供应链对接' },
      { budget_item: '劳务费', budget_amount: 4500, remark: '开发运营团队劳务补贴' },
    ],
    description: '适用于互联网+大赛高教主赛道、青年红色筑梦之旅赛道申报。',
    tags: ['互联网+', '创新创业', '平台型项目', '商业落地'],
  },
]
