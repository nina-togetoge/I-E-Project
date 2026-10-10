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

export function calculateWeightedScore(dimScores: DimScores): number {
  return scoringCriteria.reduce((sum, c) => sum + (dimScores[c.key] || 0) * c.weight, 0)
}

export const sliderMarks: Record<number, any> = {
  0: { label: '0' },
  25: { label: '25' },
  50: { label: '50' },
  75: { label: '75' },
  100: { label: '100' },
}
