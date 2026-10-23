/**
 * 富文本安全渲染工具
 *
 * 编辑器保存的是 HTML 片段，详情页用 v-html 展示前必须先清洗：
 * - 只保留白名单标签，其余标签拆掉但保留文字；
 * - script/style/iframe 等直接删除；
 * - 链接仅允许 http/https/mailto/站内路径，图片仅允许本站签名直链或 http(s)；
 * - 历史数据可能是纯文本，按换行转成 <br> 保留排版。
 */

const ALLOWED_TAGS = new Set([
  'P', 'BR', 'DIV', 'SPAN', 'B', 'STRONG', 'I', 'EM', 'U', 'S', 'STRIKE',
  'UL', 'OL', 'LI', 'BLOCKQUOTE', 'H1', 'H2', 'H3', 'H4', 'HR',
  'A', 'IMG', 'TABLE', 'THEAD', 'TBODY', 'TR', 'TD', 'TH',
])

const ALLOWED_ATTRS: Record<string, string[]> = {
  A: ['href', 'title'],
  IMG: ['src', 'alt'],
}

const DANGEROUS_TAGS = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'FORM', 'INPUT'])

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function isSafeHref(href: string): boolean {
  return /^(https?:|mailto:|\/)/i.test(href)
}

function isSafeImageSrc(src: string): boolean {
  return /^(\/api\/files\/img\/|https?:\/\/)/i.test(src)
}

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

/** 把富文本内容转换为可安全用于 v-html 的 HTML */
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
