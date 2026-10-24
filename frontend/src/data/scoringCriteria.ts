/**
 * 专家评审评分指标配置
 *
 * 模块职责：
 *  - 定义盲审评分的维度、权重与说明，评审页据此动态渲染滑动条/输入框，
 *    并按 calculateWeightedScore 汇总为百分制总分。
 *  - 与后端评分口径保持一致，前端只负责展示与即时计算，最终分数仍以后端落库为准。
 *
 * 使用方：评审中心（专家评分面板）、评审详情页、后台评分统计。
 * 关键约定：四个维度的 weight 之和必须为 1，否则加权总分不会落在 0~100 区间。
 */

/** 单个评分维度的结构 */
export interface ScoringCriterion {
  /** 维度标识，与后端评分字段 key 对应（如 innovation） */
  key: string
  /** 维度展示名称，直接用于表单标签 */
  name: string
  /** 权重（0~1 小数），所有维度合计为 1 */
  weight: number
  /** 维度评分说明，作为输入框/滑动条的提示文案 */
  desc: string
}

/**
 * 盲审评分维度清单（满分 100，按权重加权）。
 * 顺序即评审页的展示顺序。
 */
export const scoringCriteria: ScoringCriterion[] = [
  {
    key: 'innovation',
    name: '创新性',
    weight: 0.30,
    desc: '项目方案的创新程度、技术新颖性',
  },
  {
    key: 'feasibility',
    name: '可行性',
    weight: 0.30,
    desc: '技术路线、团队能力、进度安排合理性',
  },
  {
    key: 'team',
    name: '团队实力',
    weight: 0.20,
    desc: '成员结构、指导教师、前期基础',
  },
  {
    key: 'market',
    name: '应用价值',
    weight: 0.20,
    desc: '市场前景、社会价值、落地可能性',
  },
]

/**
 * 各维度得分映射：key 对应 ScoringCriterion.key，value 为该维度 0~100 的原始分。
 * 缺少某个维度时按 0 分参与加权。
 */
export type DimScores = Record<string, number>

/** 专家评审及格线（与后端 config.EXPERT_PASS_SCORE 保持一致），总分达到该值且意见合规才可判定通过 */
export const EXPERT_PASS_SCORE = 60

/** 判定为通过时评审意见的最小字符数（与后端校验保持一致），避免出现“同意”这类无信息量评语 */
export const EXPERT_PASS_COMMENT_MIN = 10

/**
 * 计算加权总分。
 * @param dimScores 各维度原始得分，缺省维度按 0 计算
 * @returns 百分制加权总分，四舍五入保留 2 位小数
 * 说明：后端 score 为 Decimal 且最多 2 位小数，这里主动取整避免浮点误差导致前后端展示不一致。
 */
export function calculateWeightedScore(dimScores: DimScores): number {
  const sum = scoringCriteria.reduce((s, c) => s + (dimScores[c.key] || 0) * c.weight, 0)
  // 权重为小数时 sum 会产生浮点误差（如 82.50000000000001），
  // 后端 score 为 Decimal 且限制最多 2 位小数，需四舍五入到 2 位。
  return Math.round(sum * 100) / 100
}

/**
 * Element Plus slider 的刻度文案，0~100 每 25 分一档。
 * 仅作为评审页滑动条的视觉参考，不参与分数计算。
 */
export const sliderMarks: Record<number, any> = {
  0: { label: '0' },
  25: { label: '25' },
  50: { label: '50' },
  75: { label: '75' },
  100: { label: '100' },
}
