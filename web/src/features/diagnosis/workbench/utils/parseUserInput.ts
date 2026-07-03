import type { DiagnoseRequest } from '../types/diagnosis'

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function stripControlTokens(text: string): string {
  return text
    .replace(/\bcase[_-]?id\s*[:=]\s*[A-Za-z0-9_-]+/gi, '')
    .replace(/\bdata[_-]?dir\s*[:=]\s*[^\s，,。；;]+/gi, '')
}

function cleanSymptom(value: string): string {
  return value
    .replace(/^[\s：:，,。；;]+/, '')
    .replace(/[\s，,。；;.!！?？]+$/, '')
    .trim()
}

function extractExplicitSymptom(text: string, api: string): string | null {
  const cleaned = stripControlTokens(text)
  const apiPattern = escapeRegExp(api)
  const match = cleaned.match(new RegExp(`${apiPattern}\\s*接口(?:出现|发生|报出|报)?\\s*([\\s\\S]*?)(?:请分析|请帮|帮我分析|$)`, 'i'))
  if (!match?.[1]) return null
  const symptom = cleanSymptom(match[1])
  return symptom || null
}

function extractLabeledValue(text: string, labelPattern: string): string | null {
  const labels = 'api|time|symptom|case[_-]?id|data[_-]?dir'
  const match = text.match(new RegExp(`\\b${labelPattern}\\s*[:=]\\s*([\\s\\S]*?)(?=\\s+\\b(?:${labels})\\s*[:=]|$)`, 'i'))
  const value = cleanSymptom(match?.[1] ?? '')
  return value || null
}

/** Parse free-form user input into structured DiagnoseRequest fields.
 *  case_id and data_dir are internal concepts not exposed to end users;
 *  they are never parsed from natural-language input.
 */
export function parseUserInput(text: string): DiagnoseRequest {
  const time = extractLabeledValue(text, 'time')
    ?? text.match(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)?.[0]
    ?? '2026-04-10 10:51:14'
  const api = extractLabeledValue(text, 'api')
    ?? text.match(/\/[^\s，。,.\uff0c\uff01！？?]+/)?.[0]
    ?? ''

  const base = {
    api,
    time,
  }

  const explicitSymptom = extractLabeledValue(text, 'symptom') ?? extractExplicitSymptom(text, api)
  if (explicitSymptom) {
    return { ...base, symptom: explicitSymptom }
  }

  const httpMatch = text.match(/HTTP\s*\d{3}/i)
  if (httpMatch) {
    return { ...base, symptom: httpMatch[0].toUpperCase().replace(/\s+/, ' ') }
  }
  if (/超时|timeout|响应慢|slow/i.test(text)) {
    return { ...base, symptom: '请求超时' }
  }
  if (/报错|异常|exception|error/i.test(text)) {
    return { ...base, symptom: '服务异常' }
  }
  if (/不可用|down|挂了|宕机/i.test(text)) {
    return { ...base, symptom: '服务不可用' }
  }
  return { ...base, symptom: 'HTTP 500' }
}