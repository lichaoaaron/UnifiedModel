import React, { Fragment, createContext, useContext, useMemo, type ReactNode } from 'react';
import { config } from '@grafana/runtime';
import { enUS } from './locales/en-US';
import { zhCN } from './locales/zh-CN';

// Ported from web/src/i18n/index.tsx with two deliberate differences:
// - The locale follows the Grafana user's language preference instead of
//   navigator.language + localStorage. Grafana owns locale selection, so the
//   plugin ships no LanguageSelect switcher and no setLocale.
// - No document.documentElement.lang writes — the document belongs to Grafana.

export type MessageKey = keyof typeof enUS;
export type MessageParams = Record<string, string | number>;
export type RichTextRenderer = (chunks: ReactNode) => ReactNode;
export type RichTextRenderers = Record<string, RichTextRenderer>;

export interface TFunction {
  (key: MessageKey, params?: MessageParams): string;
  rich: (key: MessageKey, renderers: RichTextRenderers, params?: MessageParams) => ReactNode;
}

export type Locale = 'en-US' | 'zh-CN';

const defaultLocale: Locale = 'en-US';

const messages = {
  'en-US': enUS,
  'zh-CN': zhCN,
} satisfies Record<Locale, Partial<Record<MessageKey, string>>>;

interface I18nContextValue {
  locale: Locale;
  t: TFunction;
}

const I18nContext = createContext<I18nContextValue | null>(null);

// Grafana reports BCP-47 tags like `zh-Hans`/`zh-Hant`; anything Chinese maps
// to the zh-CN dictionary, everything else falls back to en-US. The optional
// chaining matters: config.bootData is undefined under jest.
function detectLocale(): Locale {
  const language = config.bootData?.user?.language?.toLowerCase() ?? '';
  return language.startsWith('zh') ? 'zh-CN' : defaultLocale;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const value = useMemo<I18nContextValue>(() => {
    const locale = detectLocale();
    const t = ((key, params) => interpolate(getMessage(locale, key), params)) as TFunction;
    t.rich = (key, renderers, params) => renderRichMessage(getMessage(locale, key), renderers, params);
    return { locale, t };
  }, []);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const value = useContext(I18nContext);
  if (!value) {
    throw new Error('useI18n must be used inside I18nProvider');
  }
  return value;
}

function getMessage(locale: Locale, key: MessageKey) {
  return messages[locale][key] ?? enUS[key];
}

function interpolate(template: string, params?: MessageParams) {
  if (!params) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    const value = params[key];
    return value === undefined ? match : String(value);
  });
}

type RichMessagePart = string | { tag: string; children: RichMessagePart[] };

function renderRichMessage(template: string, renderers: RichTextRenderers, params?: MessageParams) {
  const parts = parseRichMessage(template);
  if (!parts) {
    return interpolate(template, params);
  }
  return renderRichParts(parts, renderers, params);
}

function parseRichMessage(template: string): RichMessagePart[] | null {
  const root = { tag: '', children: [] as RichMessagePart[] };
  const stack = [root];
  const tokens = template.split(/(<\/?[A-Za-z][\w-]*>)/g).filter(Boolean);

  for (const token of tokens) {
    const open = token.match(/^<([A-Za-z][\w-]*)>$/);
    if (open) {
      stack.push({ tag: open[1], children: [] });
      continue;
    }

    const close = token.match(/^<\/([A-Za-z][\w-]*)>$/);
    if (close) {
      const current = stack.pop();
      if (!current || current.tag !== close[1]) {
        return null;
      }
      stack[stack.length - 1].children.push(current);
      continue;
    }

    stack[stack.length - 1].children.push(token);
  }

  return stack.length === 1 ? root.children : null;
}

function renderRichParts(
  parts: RichMessagePart[],
  renderers: RichTextRenderers,
  params: MessageParams | undefined,
  path = 'r'
): ReactNode[] {
  return parts.map((part, index) => {
    const key = `${path}-${index}`;
    if (typeof part === 'string') {
      return <Fragment key={key}>{interpolate(part, params)}</Fragment>;
    }

    const children = renderRichParts(part.children, renderers, params, key);
    const content = children.length === 1 ? children[0] : children;
    const rendered = renderers[part.tag]?.(content) ?? content;
    return <Fragment key={key}>{rendered}</Fragment>;
  });
}
