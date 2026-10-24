/**
 * 统一表单校验工具
 * 毕设级严谨：前后端使用完全一致的正则规则
 *
 *  - 手机号：11位，首位1，第二位3-9，中国大陆格式  r"^1[3-9]\d{9}$"
 *  - 邮箱  ：RFC简化版（含@、前后非空、域有点、TLD 2-16字母）
 *  - 密码  ：严格6位纯数字，不得多不得少，不得含字母/符号  r"^\d{6}$"
 *
 * 导出三类内容：
 *  1. REGEX_*  正则常量（供复用、供后端Pydantic pattern参数对齐）
 *  2. is_*(value) 纯布尔函数（供代码判断、导入预览标红）
 *  3. validate_*(rule, value, cb) Element Plus FormRules 自定义校验函数
 */

/* ============================================================
 *  一、正则常量（必须与 backend/app/schemas/user.py 保持一字不差）
 * ============================================================ */

/** 密码：严格 6 位数字，不多不少不含字母符号 */
export const REGEX_PASSWORD_6_DIGITS = /^\d{6}$/

/** 中国大陆手机号：11位数字，首 1，第二位 3-9 */
export const REGEX_PHONE_CN = /^1[3-9]\d{9}$/

/**
 * 邮箱：简化 RFC，覆盖校园邮箱常见场景
 *  - 本地部分：字母数字 + ._-+
 *  - 必须 @
 *  - 域名部分：字母数字.-，至少一个 . 分隔 TLD
 *  - TLD：2~16 纯字母
 */
export const REGEX_EMAIL = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,16}$/

/* ============================================================
 *  二、输入归一化（按照经验371256：校验前统一清洗，避免空格/全角）
 *
 *  【毕设级严格策略】手机号必须是纯11位数字与后端Pydantic pattern一字不差对齐
 *  - 剥掉空白后，再判断是否含有非数字字符 → 直接报错不宽容横线
 *  - 原因：如果我们在校验器里偷偷把 "138-1234-5678" 归一化为 13812345678 判通过，
 *    但表单模型里用户提交给后端的仍是 "138-1234-5678" → 后端正则不包含 "-" → 422 →
 *    "校验通过但提交失败"，也就是371256经验里的校验/提交值不一致大坑。
 *  因此正确做法：严格要求原始输入（去掉空白后）是纯数字字符串。
 * ============================================================ */

/** 仅去除空白（全角空格、普通空格、制表、换行） */
export function normalizePhone(raw: unknown): string {
  let s = raw == null ? '' : String(raw)
  s = s.replace(/[\s\u3000]/g, '')
  return s
}

/** 邮箱归一化：trim + 小写 */
export function normalizeEmail(raw: unknown): string {
  return raw == null ? '' : String(raw).trim().toLowerCase()
}

/** 密码归一化：只去前后空白，中间空格视为非法（6位纯数字不含空格） */
export function normalizePassword(raw: unknown): string {
  return raw == null ? '' : String(raw).trim()
}

/* ============================================================
 *  三、布尔判断函数（导入预览、代码分支判断用）
 *  手机号：严格模式，必须去空白后是纯数字+长度11+pattern通过
 * ============================================================ */

/**
 * 判断密码是否为严格 6 位纯数字。
 * @returns 合法返回 true；空字符串、含字母/符号、位数不足均返回 false
 */
export function isValidPassword(v: unknown): boolean {
  return REGEX_PASSWORD_6_DIGITS.test(normalizePassword(v))
}

/**
 * 判断手机号是否合法。
 * @returns 空值视为合法（可选字段）；非空时必须是去除空白后的 11 位纯数字且符合大陆号段
 */
export function isValidPhone(v: unknown): boolean {
  const s = normalizePhone(v)
  if (s === '') return true  // 空手机号在可选字段合法
  // 严格：去除空白后必须全部是数字，否则不合格
  if (!/^\d+$/.test(s)) return false
  return REGEX_PHONE_CN.test(s)
}

/**
 * 判断邮箱是否合法。
 * @returns 空值视为合法（可选字段）；非空时按简化 RFC 正则校验
 */
export function isValidEmail(v: unknown): boolean {
  // 空邮箱在可选字段是合法的，这里只判断"非空时是否合法"
  const e = normalizeEmail(v)
  if (e === '') return true
  return REGEX_EMAIL.test(e)
}

/* ============================================================
 *  四、Element Plus 自定义校验器
 *     签名：(rule, value, cb) => void
 *     optional=true 时，空值直接放行（cb()）；非空再校验
 * ============================================================ */

/** Element Plus 传入的 rule 对象中本项目实际用到的字段，仅作类型收敛 */
type RuleLike = { required?: boolean; message?: string; field?: string }
/** 校验回调：传 Error 表示失败，空调用表示通过 */
type Callback = (e?: Error) => void

/**
 * 生成必填校验器：空字符串/undefined/null 拦截，白名单之外的纯空白也视为空。
 * @param label 字段中文名，用于拼接提示语“请输入xx”
 */
export function requiredValidator(label: string) {
  return (_rule: RuleLike, value: unknown, cb: Callback) => {
    const v = value == null ? '' : String(value).trim()
    if (v === '') cb(new Error(`请输入${label}`))
    else cb()
  }
}

/** 密码校验：严格6位纯数字。required=true时空值先报"请输入密码" */
export function passwordValidator(required = true, label = '密码') {
  return (_rule: RuleLike, value: unknown, cb: Callback) => {
    const v = normalizePassword(value)
    if (v === '') {
      if (required) cb(new Error(`请输入${label}`))
      else cb()
      return
    }
    if (!REGEX_PASSWORD_6_DIGITS.test(v)) {
      cb(new Error(`${label}必须是6位纯数字`))
      return
    }
    cb()
  }
}

/** 手机号校验。required=false 时允许空 */
export function phoneValidator(required = false, label = '手机号') {
  return (_rule: RuleLike, value: unknown, cb: Callback) => {
    const v = normalizePhone(value)
    if (v === '') {
      if (required) cb(new Error(`请输入${label}`))
      else cb()
      return
    }
    if (!/^\d+$/.test(v)) {
      cb(new Error(`${label}仅需11位纯数字，请勿添加空格、横线、括号等符号`))
      return
    }
    if (!REGEX_PHONE_CN.test(v)) {
      cb(new Error(`${label}格式不正确：应为11位中国大陆手机号（1开头，第2位3-9）`))
      return
    }
    cb()
  }
}

/** 邮箱校验。required=false 时允许空 */
export function emailValidator(required = false, label = '邮箱') {
  return (_rule: RuleLike, value: unknown, cb: Callback) => {
    const v = normalizeEmail(value)
    if (v === '') {
      if (required) cb(new Error(`请输入${label}`))
      else cb()
      return
    }
    if (!REGEX_EMAIL.test(v)) {
      cb(new Error(`${label}格式不正确`))
      return
    }
    cb()
  }
}

/**
 * 生成“两次密码一致”校验器，配合修改密码场景使用。
 * @param getNewPwd 惰性读取新密码的函数，避免把旧值闭包进校验器
 * @param label 确认密码字段的展示名
 * 边界：确认密码为空时优先提示“请再次输入”，而不是提示不一致。
 */
export function confirmPasswordValidator(getNewPwd: () => string, label = '确认密码') {
  return (_rule: RuleLike, value: unknown, cb: Callback) => {
    const v = normalizePassword(value)
    if (v === '') {
      cb(new Error(`请再次输入${label}`))
      return
    }
    if (v !== normalizePassword(getNewPwd())) {
      cb(new Error('两次密码输入不一致'))
      return
    }
    cb()
  }
}
