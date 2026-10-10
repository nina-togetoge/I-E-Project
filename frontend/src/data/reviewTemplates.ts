export interface ReviewTemplate {
  label: string
  text: string
  category: 'pass' | 'reject' | 'common'
}

export const reviewTemplates: ReviewTemplate[] = [
  {
    label: '通过模板1',
    text: '方案思路清晰，创新点明确，同意立项。',
    category: 'pass',
  },
  {
    label: '通过模板2',
    text: '团队配置合理，预算编制规范，建议通过。',
    category: 'pass',
  },
  {
    label: '通过模板3',
    text: '项目具有较好的应用前景和实践价值，评审通过。',
    category: 'pass',
  },
  {
    label: '通过模板4',
    text: '技术路线可行，进度安排合理，同意立项支持。',
    category: 'pass',
  },
  {
    label: '通过模板5',
    text: '前期基础扎实，指导教师配备到位，建议优先立项。',
    category: 'pass',
  },
  {
    label: '驳回模板1',
    text: '创新点不足，建议补充差异化说明后再申报。',
    category: 'reject',
  },
  {
    label: '驳回模板2',
    text: '预算科目不合理，需重新编制。',
    category: 'reject',
  },
  {
    label: '驳回模板3',
    text: '技术路线描述不清晰，可行性论证不足，请补充完善。',
    category: 'reject',
  },
  {
    label: '驳回模板4',
    text: '团队成员结构不合理，缺少核心技术人员，请调整后重新提交。',
    category: 'reject',
  },
  {
    label: '驳回模板5',
    text: '项目方案与同类项目重复，缺乏独特性，请重新梳理创新点。',
    category: 'reject',
  },
  {
    label: '驳回模板6',
    text: '预期成果量化不足，难以考核，请补充可衡量的成果指标。',
    category: 'reject',
  },
  {
    label: '驳回模板7',
    text: '进度安排过于紧张，难以按计划完成，请合理调整时间节点。',
    category: 'reject',
  },
  {
    label: '驳回模板8',
    text: '市场调研不充分，应用价值论证薄弱，请补充调研数据。',
    category: 'reject',
  },
]
