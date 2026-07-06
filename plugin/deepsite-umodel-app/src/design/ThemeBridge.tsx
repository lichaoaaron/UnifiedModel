import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { GrafanaTheme2 } from '@grafana/data';
import { useTheme2 } from '@grafana/ui';
import './components.css';

// Maps the standalone web app's `--om-*` design tokens onto the active Grafana
// theme. Setting them as CSS custom properties on a wrapper lets the ported
// `om-*` / `ume-*` stylesheets follow Grafana's light/dark theme unchanged.
function buildThemeVars(theme: GrafanaTheme2): Record<string, string> {
  return {
    '--om-bg': theme.colors.background.canvas,
    '--om-surface': theme.colors.background.primary,
    '--om-surface-subtle': theme.colors.background.secondary,
    '--om-surface-raised': theme.colors.background.primary,
    '--om-text': theme.colors.text.primary,
    '--om-text-muted': theme.colors.text.secondary,
    '--om-text-faint': theme.colors.text.disabled,
    '--om-border': theme.colors.border.weak,
    '--om-border-strong': theme.colors.border.medium,
    '--om-primary': theme.colors.primary.main,
    '--om-primary-strong': theme.colors.primary.shade,
    '--om-primary-soft': theme.colors.primary.transparent,
    '--om-primary-border': theme.colors.primary.border,
    '--om-primary-ring': theme.colors.primary.transparent,
    '--om-accent': theme.colors.primary.main,
    '--om-accent-strong': theme.colors.primary.shade,
    '--om-accent-soft': theme.colors.primary.transparent,
    '--om-text-inverse': theme.colors.primary.contrastText,
    '--om-indigo': theme.colors.primary.main,
    '--om-indigo-soft': theme.colors.primary.transparent,
    '--om-coral': theme.colors.error.main,
    '--om-coral-soft': theme.colors.error.transparent,
    '--om-amber': theme.colors.warning.main,
    '--om-amber-soft': theme.colors.warning.transparent,
    '--om-amber-text': theme.colors.warning.text,
    '--om-red': theme.colors.error.main,
    '--om-red-soft': theme.colors.error.transparent,
    '--om-red-text': theme.colors.error.text,
    // Semantic status families for data-viz (severity/status), derived from
    // Grafana's semantic colors so meaning (red=error, amber=warning,
    // green=success, blue=primary/entry) survives and both themes are tuned.
    '--om-primary-text': theme.colors.primary.text,
    '--om-success': theme.colors.success.main,
    '--om-success-soft': theme.colors.success.transparent,
    '--om-success-text': theme.colors.success.text,
    '--om-shadow-sm': theme.shadows.z1,
    '--om-shadow-md': theme.shadows.z3,
    '--om-shadow-panel': theme.shadows.z1,
    '--om-shadow-control': theme.shadows.z1,
    '--om-radius': theme.shape.radius.default,
    '--om-radius-panel': '18px',
    '--om-radius-sm': theme.shape.radius.default,
    '--om-radius-xs': '4px',
    '--om-panel-overlap': '18px',
    '--om-panel-border': theme.colors.border.weak,
    '--om-focus-ring': theme.colors.primary.transparent,
    // Modal/overlay scrim — heavier in dark mode so the dimmed backdrop reads
    // against dark content (a fixed light-theme rgba would be invisible there).
    '--om-scrim': theme.isDark ? 'rgba(0, 0, 0, 0.55)' : 'rgba(31, 33, 32, 0.28)',
    '--om-sidebar-item-height': '38px',
    '--om-sidebar-item-font-size': '14px',
    '--om-sidebar-row-font-size': '13px',
    '--om-sidebar-meta-font-size': '12px',
    '--om-sidebar-section-font-size': '11px',
    '--om-sidebar-icon-size': '16px',
    '--om-mono': theme.typography.fontFamilyMonospace,
    // CJK-aware stack for Chinese UI copy: prefer the platform CJK faces, then
    // fall back to the active Grafana font family.
    '--om-cjk-font': `"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", ${theme.typography.fontFamily}`,
  };
}

// Themed wrapper providing the `--om-*` variables to ported UModel UI. Pages
// render their content inside it (see WorkspacePage).
export function UModelRoot({ children, className }: { children: React.ReactNode; className?: string }) {
  const theme = useTheme2();
  const vars = useMemo(() => buildThemeVars(theme), [theme]);
  const rootRef = useRef<HTMLDivElement>(null);
  // Grafana's PluginPage renders its content inside a *growing* scroll container
  // (`.page-scrollbar-content` is min-height:100%), so height:100% there is
  // circular and doesn't bound anything — the whole page scrolls. Instead pin the
  // root to exactly "from its own top to the viewport bottom" so full-height pages
  // (topology/umodel/query) fill the viewport and scroll their own panels, while
  // shorter native pages just don't fill it. The top offset (Grafana top nav +
  // page header) isn't a constant, so measure it.
  const [contentHeight, setContentHeight] = useState<number | null>(null);
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) {
      return;
    }
    const update = () => {
      const top = el.getBoundingClientRect().top;
      setContentHeight(Math.max(240, Math.floor(window.innerHeight - top)));
    };
    update();
    // Re-measure after layout settles (async page header / breadcrumbs) and on resize.
    const raf = requestAnimationFrame(update);
    window.addEventListener('resize', update);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', update);
    };
  }, []);

  // Also expose the tokens on <body> so content portaled out of this subtree
  // (the explorer's node-menu / focus-panel popovers render into document.body)
  // follows the active theme too. Only `--om-*` custom properties are set, which
  // Grafana's own styles never read, so this does not affect Grafana visuals.
  useEffect(() => {
    const { style } = document.body;
    const keys = Object.keys(vars);
    keys.forEach((k) => style.setProperty(k, vars[k]));
    return () => keys.forEach((k) => style.removeProperty(k));
  }, [vars]);

  // `height` is the measured viewport-remainder (see above); until measured, fall
  // back to 100% so nothing collapses. No overflow:hidden here so a taller-than-
  // viewport native page still scrolls via Grafana's own scroll container.
  return (
    <div
      ref={rootRef}
      className={`umodel-root${className ? ` ${className}` : ''}`}
      style={{ ...(vars as React.CSSProperties), height: contentHeight ? `${contentHeight}px` : '100%', minHeight: 0 }}
    >
      {children}
    </div>
  );
}
