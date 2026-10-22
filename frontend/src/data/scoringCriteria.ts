export interface ScoringCriterion {
  key: string
  name: string
  weight: number
  desc: string
}

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

export type DimScores = Record<string, number>

/** 专家评审及格线（与后端 config.EXPERT_PASS_SCORE 保持一致） */
export const EXPERT_PASS_SCORE = 60

/** 判定为通过时评审意见的最小字符数（与后端校验保持一致） */
export const EXPERT_PASS_COMMENT_MIN = 10

export function calculateWeightedScore(dimScores: DimScores): number {
  const sum = scoringCriteria.reduce((s, c) => s + (dimScores[c.key] || 0) * c.weight, 0)
  // 权重为小数时 sum 会产生浮点误差（如 82.50000000000001），
  // 后端 score 为 Decimal 且限制最多 2 位小数，需四舍五入到 2 位。
  return Math.round(sum * 100) / 100
}

export const sliderMarks: Record<number, any> = {
  0: { label: '0' },
  25: { label: '25' },
  50: { label: '50' },
  75: { label: '75' },
  100: { label: '100' },
}
