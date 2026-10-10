/**
 * 搜索联想 / 关键词建议 composable
 * 功能：历史搜索（localStorage）+ 热门关键词 + 实时补全
 */
import { ref } from 'vue'

const HISTORY_KEY = 'search_history'
const MAX_HISTORY = 10

const HOT_KEYWORDS = [
  '人工智能',
  '大创',
  '互联网+',
  '挑战杯',
  '创新创业',
  '乡村振兴',
  '新能源',
  '元宇宙',
  '区块链',
  'AI教育',
]

export interface SuggestionItem {
  value: string
  source: 'history' | 'hot'
  label: string
  icon: string
}

function loadHistory(): string[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (raw) {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr)) return arr.filter((x) => typeof x === 'string')
    }
  } catch {
    // ignore
  }
  return []
}

function saveHistory(list: string[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(list))
  } catch {
    // ignore
  }
}

export function useSearchSuggestions() {
  const history = ref<string[]>(loadHistory())

  function suggestions(keyword: string): SuggestionItem[] {
    const kw = (keyword || '').trim().toLowerCase()
    const result: SuggestionItem[] = []
    const seen = new Set<string>()
    const historyItems = kw
      ? history.value.filter((h) => h.toLowerCase().includes(kw))
      : history.value
    for (const h of historyItems) {
      if (!seen.has(h)) {
        seen.add(h)
        result.push({ value: h, source: 'history', label: h, icon: '⏱️' })
      }
      if (result.length >= 8) return result
    }
    const hotItems = kw
      ? HOT_KEYWORDS.filter((h) => h.toLowerCase().includes(kw))
      : HOT_KEYWORDS
    for (const h of hotItems) {
      if (!seen.has(h)) {
        seen.add(h)
        result.push({ value: h, source: 'hot', label: h, icon: '🔥' })
      }
      if (result.length >= 8) return result
    }
    return result
  }

  const hotKeywords = HOT_KEYWORDS

  function addHistory(keyword: string) {
    const kw = (keyword || '').trim()
    if (!kw) return
    let list = history.value.filter((x) => x !== kw)
    list.unshift(kw)
    list = list.slice(0, MAX_HISTORY)
    history.value = list
    saveHistory(list)
  }

  function clearHistory() {
    history.value = []
    saveHistory([])
  }

  return {
    history,
    suggestions,
    hotKeywords,
    addHistory,
    clearHistory,
  }
}
