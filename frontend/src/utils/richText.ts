/**
 * 富文本安全渲染工具
 *
 * 编辑器保存的是 HTML 片段，详情页用 v-html 展示前必须先清洗：
 * - 只保留白名单标签，其余标签拆掉但保留文字；
 * - script/style/iframe 等直接删除；
 * - 链接仅允许 http/https/mailto/站内路径，图片仅允许本站签名直链或 http(s)；
 * - 历史数据可能是纯文本，按换行转成 <br> 保留排版。
 *
 * 使用方：项目详情、评审意见、公告正文等需要展示富文本的页面，在 v-html 前调用 toSafeHtml。
 * 约定：本模块只做展示侧防护，不替代后端入库校验；返回的是可直接放进 v-html 的字符串。
 */

/** 允许保留的标签白名单（覆盖编辑器常用排版能力），其余标签会被拆壳保留文字 */
const ALLOWED_TAGS = new Set([
  'P', 'BR', 'DIV', 'SPAN', 'B', 'STRONG', 'I', 'EM', 'U', 'S', 'STRIKE',
  'UL', 'OL', 'LI', 'BLOCKQUOTE', 'H1', 'H2', 'H3', 'H4', 'HR',
  'A', 'IMG', 'TABLE', 'THEAD', 'TBODY', 'TR', 'TD', 'TH',
])

/**
 * 各标签允许保留的属性白名单。
 * 未列出的标签一律清除全部属性；A/IMG 的属性还会在下方做协议与来源二次校验。
 */
const ALLOWED_ATTRS: Record<string, string[]> = {
  A: ['href', 'title'],
  IMG: ['src', 'alt'],
}

/** 危险标签：连同内部内容整体删除，避免脚本执行、样式污染或表单注入 */
const DANGEROUS_TAGS = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'FORM', 'INPUT'])

/**
 * HTML 实体转义，用于纯文本分支与异常兜底，防止文本中的 < > 被当作标签解析。
 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * 判断链接是否安全：仅放行 http/https、mailto 与站内绝对路径（/ 开头）。
 * 显式拒绝 javascript:、data: 等可执行协议。
 */
function isSafeHref(href: string): boolean {
  return /^(https?:|mailto:|\/)/i.test(href)
}

/**
 * 判断图片地址是否安全：仅放行后端签名图片接口（/api/files/img/）或 http(s) 外链。
 * 后端附件实体文件不直接暴露路径，前端通过该签名接口或完整 URL 访问。
 */
function isSafeImageSrc(src: string): boolean {
  return /^(\/api\/files\/img\/|https?:\/\/)/i.test(src)
}

/**
 * 递归清洗节点子树：删除危险标签、拆除非白名单标签、清理多余属性并校验链接/图片。
 * 直接原地修改传入节点（DOMParser 生成的临时文档），无返回值。
 */
function sanitizeChildren(node: Element) {
  const doc = node.ownerDocument
  Array.from(node.childNodes).forEach((child) => {
    if (child.nodeType === Node.TEXT_NODE) return
    if (child.nodeType !== Node.ELEMENT_NODE) {
      child.remove()
      return
    }
    const el = child as Element
    const tag = el.tagName.toUpperCase()

    if (DANGEROUS_TAGS.has(tag)) {
      el.remove()
      return
    }
    sanitizeChildren(el)

    if (!ALLOWED_TAGS.has(tag)) {
      // 非白名单标签：保留文字内容，去掉标签本身
      const frag = doc.createDocumentFragment()
      while (el.firstChild) frag.appendChild(el.firstChild)
      el.replaceWith(frag)
      return
    }

    const allowed = ALLOWED_ATTRS[tag] || []
    Array.from(el.attributes).forEach((attr) => {
      if (!allowed.includes(attr.name.toLowerCase())) el.removeAttribute(attr.name)
    })

    if (tag === 'A') {
      const href = el.getAttribute('href') || ''
      if (!href || !isSafeHref(href)) {
        el.removeAttribute('href')
      } else {
        el.setAttribute('target', '_blank')
        el.setAttribute('rel', 'noopener noreferrer')
      }
    }
    if (tag === 'IMG') {
      const src = el.getAttribute('src') || ''
      if (!src || !isSafeImageSrc(src)) {
        el.remove()
        return
      }
      el.setAttribute('loading', 'lazy')
    }
  })
}

/**
 * 把富文本内容转换为可安全用于 v-html 的 HTML。
 *
 * 处理流程：
 * - 空值返回空字符串；
 * - 不含标签的历史纯文本：转义后把换行替换为 <br>，保留原有排版；
 * - 含标签：用 DOMParser 解析到临时文档，再递归走白名单清洗；
 * - 解析或清洗异常时降级为“转义 + 换行”，保证页面不白屏、不注入。
 * @param raw 后端返回的富文本 HTML 或纯文本
 * @returns 已清洗、可直接绑定 v-html 的字符串
 * 注意：依赖浏览器 DOM API，仅可在前端运行环境调用。
 */
export function toSafeHtml(raw?: string | null): string {
  if (!raw) return ''
  const text = String(raw)
  // 不含标签的历史纯文本：转义后保留换行
  if (!/<[a-z][\s\S]*>/i.test(text)) {
    return escapeHtml(text).replace(/\r?\n/g, '<br>')
  }
  try {
    const doc = new DOMParser().parseFromString(`<div id="rich-root">${text}</div>`, 'text/html')
    const root = doc.getElementById('rich-root')
    if (!root) return ''
    sanitizeChildren(root)
    return root.innerHTML
  } catch (_) {
    return escapeHtml(text).replace(/\r?\n/g, '<br>')
  }
}
