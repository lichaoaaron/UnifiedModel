import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import ReactDOM from 'react-dom'
import { CircleDashed, Crosshair, Trash2, X } from 'lucide-react'
import type { MModelElement } from '../../api/types'
import {
  colorForKind,
  elementKey,
  kindActsAsGraphNode,
  linkKinds,
  summarize,
  titleForElement,
  type BackgroundStyle,
  type DraftDiff,
  type EntitySetLinkDisplay,
  type ViewMode,
} from './model'

export function SummarySidebar({
  stats,
  diff,
  kindFilters,
  domainFilters,
  currentView,
  entitySetLinkDisplay,
  onFocusDraftChanges,
  onToggleKind,
  onToggleDomain,
}: {
  stats: ReturnType<typeof summarize>
  diff: DraftDiff
  kindFilters: string[]
  domainFilters: string[]
  currentView: ViewMode
  entitySetLinkDisplay: EntitySetLinkDisplay
  onFocusDraftChanges: () => void
  onToggleKind: (kind: string) => void
  onToggleDomain: (domain: string) => void
}) {
  const diffTotal = diff.added.length + diff.modified.length + diff.deleted.length
  const focusableDiffCount = diff.added.length + diff.modified.length
  const kindIsNodeFilter = (kind: string) => (
    currentView === 'graph' ? kindActsAsGraphNode(kind, entitySetLinkDisplay) : !linkKinds.has(kind)
  )
  const nodeKindEntries = stats.kindEntries.filter(([kind]) => kindIsNodeFilter(kind))
  const linkKindEntries = stats.kindEntries.filter(([kind]) => !kindIsNodeFilter(kind))
  return (
    <div className="ume-sidebar-body">
      <div className="ume-stat-grid">
        <StatCard label="Nodes" value={stats.nodes} />
        <StatCard label="Links" value={stats.links} />
      </div>

      {diffTotal > 0 && (
        <button
          className="ume-diff-card"
          disabled={focusableDiffCount === 0}
          onClick={onFocusDraftChanges}
          type="button"
          title={focusableDiffCount > 0 ? 'Focus added and modified draft elements' : 'Deleted elements cannot be focused'}
        >
          <span className="ume-diff-card-heading">
            <CircleDashed size={14} />
            <strong>Unsaved draft MModel</strong>
            <DraftHelpTooltip />
          </span>
          <span className="ume-diff-card-counts">
            {diff.added.length > 0 && <code className="added">+{diff.added.length} Added</code>}
            {diff.modified.length > 0 && <code className="modified">~{diff.modified.length} Modified</code>}
            {diff.deleted.length > 0 && <code className="deleted">-{diff.deleted.length} Deleted</code>}
          </span>
        </button>
      )}

      <SectionTitle>By Type</SectionTitle>
      <div className="ume-filter-list">
        {nodeKindEntries.map(([kind, count]) => {
          const color = colorForKind(kind)
          const active = kindFilters.includes(kind)
          return (
            <button
              key={kind}
              className={`ume-filter-row ${active ? 'active' : ''}`}
              onClick={() => onToggleKind(kind)}
              style={{ '--row-bg': color.bg, '--row-text': color.text } as CSSProperties}
              type="button"
            >
              <span className="ume-filter-label">
                <span className="ume-kind-dot" style={{ background: color.dot }} />
                {color.label}
              </span>
              <strong>{count}</strong>
            </button>
          )
        })}
        {linkKindEntries.length > 0 && <span className="ume-filter-list-separator" />}
        {linkKindEntries.map(([kind, count]) => {
          const color = colorForKind(kind)
          const active = kindFilters.includes(kind)
          const disabled = currentView === 'graph' && !kindActsAsGraphNode(kind, entitySetLinkDisplay)
          return (
            <button
              key={kind}
              className={`ume-filter-row ${active ? 'active' : ''}`}
              onClick={() => !disabled && onToggleKind(kind)}
              style={{ '--row-bg': color.bg, '--row-text': color.text } as CSSProperties}
              type="button"
              disabled={disabled}
              title={disabled ? 'Link filters are available in table view' : undefined}
            >
              <span className="ume-filter-label">
                <span className="ume-kind-line" style={{ background: color.dot }} />
                {color.label}
              </span>
              <strong>{count}</strong>
            </button>
          )
        })}
      </div>

      <SectionTitle>By Domain</SectionTitle>
      <div className="ume-filter-list">
        {stats.domainEntries.slice(0, 12).map(([domain, count]) => {
          const active = domainFilters.includes(domain)
          return (
            <button key={domain} className={`ume-filter-row ${active ? 'active neutral' : ''}`} onClick={() => onToggleDomain(domain)} type="button">
              <span className="ume-filter-label">
                <span className="ume-domain-dot" />
                {domain}
              </span>
              <strong>{count}</strong>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function DraftHelpTooltip() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement | null>(null)
  const rect = ref.current?.getBoundingClientRect()
  const panelWidth = 360
  const panelHeight = 166
  const gap = 12
  const fitsRight = rect ? rect.right + gap + panelWidth <= window.innerWidth - 12 : false
  const fitsLeft = rect ? rect.left - gap - panelWidth >= 12 : false
  const left = rect
    ? fitsRight
      ? rect.right + gap
      : fitsLeft
        ? rect.left - gap - panelWidth
        : Math.max(12, Math.min(rect.left, window.innerWidth - panelWidth - 12))
    : 12
  const rawTop = rect ? (fitsRight || fitsLeft ? rect.top - 18 : rect.bottom + gap) : 12
  const top = Math.min(Math.max(12, rawTop), window.innerHeight - panelHeight - 12)
  return (
    <>
      <span
        ref={ref}
        className="ume-diff-help"
        onBlur={() => setOpen(false)}
        onClick={(event) => event.stopPropagation()}
        onFocus={() => setOpen(true)}
        onMouseDown={(event) => event.preventDefault()}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        tabIndex={0}
      >
        ?
      </span>
      {open && rect && ReactDOM.createPortal(
        <div className="ume-diff-help-panel" style={{ left, top, width: panelWidth } as CSSProperties}>
          <strong>Draft focus</strong>
          <p>Click this card to focus all added and modified draft nodes or links.</p>
          <p>Deleted items cannot be focused here and only contribute to the count.</p>
          <p>Changes are applied only after <b>Confirm &amp; Submit</b>.</p>
        </div>,
        document.body,
      )}
    </>
  )
}

export function SettingsSidebar({
  backgroundStyle,
  entitySetLinkDisplay,
  forceFullMode,
  onBackgroundStyleChange,
  onEntitySetLinkDisplayChange,
  onForceFullModeChange,
}: {
  backgroundStyle: BackgroundStyle
  entitySetLinkDisplay: EntitySetLinkDisplay
  forceFullMode: boolean
  onBackgroundStyleChange: (value: BackgroundStyle) => void
  onEntitySetLinkDisplayChange: (value: EntitySetLinkDisplay) => void
  onForceFullModeChange: (value: boolean) => void
}) {
  return (
    <div className="ume-sidebar-body">
      <SectionTitle>Canvas</SectionTitle>
      <div className="ume-settings-options">
        {([
          { label: 'Plain', value: 'none' },
          { label: 'Dots', value: 'dots' },
          { label: 'Lines', value: 'lines' },
          { label: 'Grid', value: 'cross' },
        ] as const).map((option) => (
          <button
            key={option.value}
            className={backgroundStyle === option.value ? 'active' : ''}
            onClick={() => onBackgroundStyleChange(option.value)}
            type="button"
          >
            {option.label}
          </button>
        ))}
      </div>
      <SectionTitle>Relations</SectionTitle>
      <select
        className="ume-settings-select"
        value={entitySetLinkDisplay}
        onChange={(event) => onEntitySetLinkDisplayChange(event.target.value as EntitySetLinkDisplay)}
      >
        <option value="absolute_node">Connections only</option>
        <option value="relative_link">Bridge nodes</option>
      </select>
      <SectionTitle>Display</SectionTitle>
      <label className="ume-settings-check">
        <input checked={forceFullMode} onChange={(event) => onForceFullModeChange(event.target.checked)} type="checkbox" />
        Always render every item
      </label>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="ume-stat-card">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  )
}

function SectionTitle({ children }: { children: string }) {
  return <div className="ume-section-title">{children}</div>
}

export function FilterBar({
  activeCount,
  focusIds,
  fullTextFilters,
  kindFilters,
  domainFilters,
  filterStacking,
  draftElements,
  currentView,
  entitySetLinkDisplay,
  onClear,
  onRemoveFullText,
  onRemoveKind,
  onRemoveDomain,
  onRemoveFocus,
  onClearFocus,
  onToggleStacking,
}: {
  activeCount: number
  focusIds: string[]
  fullTextFilters: string[]
  kindFilters: string[]
  domainFilters: string[]
  filterStacking: boolean
  draftElements: MModelElement[]
  currentView: ViewMode
  entitySetLinkDisplay: EntitySetLinkDisplay
  onClear: () => void
  onRemoveFullText: (value: string) => void
  onRemoveKind: (value: string) => void
  onRemoveDomain: (value: string) => void
  onRemoveFocus: (value: string) => void
  onClearFocus: () => void
  onToggleStacking: () => void
}) {
  if (activeCount === 0) return null
  const hasFocus = focusIds.length > 0
  const dimmed = hasFocus && !filterStacking
  const focusItems = focusIds.map((id) => {
    const element = draftElements.find((item) => elementKey(item) === id)
    return { id, label: element ? titleForElement(element) : id }
  })
  return (
    <div className="ume-filter-bar">
      <InfoTooltip>
        <strong>Filtering</strong>
        <p><b>Focus</b> shows selected items and nearby related items.</p>
        <p><b>Stack filters</b> narrows that focused view with search, type, or domain filters.</p>
        <p>Clear filters to return to the full result.</p>
      </InfoTooltip>
      {hasFocus && (
        <FocusChip
          items={focusItems}
          onClear={onClearFocus}
          onRemove={onRemoveFocus}
        />
      )}
      {hasFocus && (
        <>
          <span className="ume-filter-separator" />
          <button className={`ume-filter-stack ${filterStacking ? 'active' : ''}`} onClick={onToggleStacking} type="button">
            <span><i /></span>
            Stack filters
          </button>
        </>
      )}
      {(fullTextFilters.length > 0 || kindFilters.length > 0 || domainFilters.length > 0) && hasFocus && (
        <span className="ume-filter-separator" />
      )}
      {fullTextFilters.map((value) => (
        <ActiveFilterChip
          key={`search-${value}`}
          label={value}
          prefix="Search:"
          dimmed={dimmed}
          onRemove={() => onRemoveFullText(value)}
        />
      ))}
      {kindFilters.map((kind) => {
        const color = colorForKind(kind)
        return (
          <ActiveFilterChip
            key={kind}
            label={color.label}
            dotColor={color.dot}
            accentColor={color.text}
            suffix={currentView === 'graph' && !kindActsAsGraphNode(kind, entitySetLinkDisplay) ? 'table only' : undefined}
            dimmed={dimmed || (currentView === 'graph' && !kindActsAsGraphNode(kind, entitySetLinkDisplay))}
            onRemove={() => onRemoveKind(kind)}
          />
        )
      })}
      {domainFilters.map((domain) => (
        <ActiveFilterChip
          key={domain}
          label={domain}
          prefix="Domain:"
          dimmed={dimmed}
          onRemove={() => onRemoveDomain(domain)}
        />
      ))}
      <span className="ume-filter-grow" />
      <button className="ume-filter-clear" onClick={onClear} type="button">
        <Trash2 size={12} />
        Clear all
      </button>
    </div>
  )
}

function InfoTooltip({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement | null>(null)
  const rect = ref.current?.getBoundingClientRect()
  const left = rect ? Math.min(Math.max(12, rect.left), window.innerWidth - 430) : 12
  const top = rect ? rect.bottom + 8 : 0
  return (
    <>
      <span
        ref={ref}
        className="ume-filter-help"
        onBlur={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        role="button"
        tabIndex={0}
      >
        ?
      </span>
      {open && rect && ReactDOM.createPortal(
        <div className="ume-info-tooltip" style={{ left, top } as CSSProperties}>
          {children}
        </div>,
        document.body,
      )}
    </>
  )
}

function FocusChip({
  items,
  onClear,
  onRemove,
}: {
  items: Array<{ id: string; label: string }>
  onClear: () => void
  onRemove: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement | null>(null)
  const timerRef = useRef<number | null>(null)
  const rect = ref.current?.getBoundingClientRect()
  const left = rect ? Math.min(Math.max(12, rect.left), window.innerWidth - 410) : 12
  const top = rect ? rect.bottom + 4 : 0

  const openPanel = () => {
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = null
    setOpen(true)
  }
  const closePanelDelayed = () => {
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => setOpen(false), 180)
  }

  useEffect(() => () => {
    if (timerRef.current) window.clearTimeout(timerRef.current)
  }, [])

  return (
    <>
      <span
        ref={ref}
        className="ume-filter-focus"
        onMouseEnter={openPanel}
        onMouseLeave={closePanelDelayed}
      >
        <Crosshair size={12} />
        Focus ({items.length})
        <button
          onClick={(event) => {
            event.stopPropagation()
            onClear()
            setOpen(false)
          }}
          type="button"
          title="Clear focus"
        >
          <X size={10} />
        </button>
      </span>
      {open && rect && ReactDOM.createPortal(
        <div
          className="ume-focus-panel"
          onMouseEnter={openPanel}
          onMouseLeave={closePanelDelayed}
          style={{ left, top } as CSSProperties}
        >
          <div className="ume-focus-panel-header">
            <strong>Focus items ({items.length})</strong>
            <button onClick={() => { onClear(); setOpen(false) }} type="button">
              Clear all
            </button>
          </div>
          {items.map((item) => (
            <div className="ume-focus-panel-row" key={item.id}>
              <span>
                <strong>{item.label}</strong>
                <code>{item.id}</code>
              </span>
              <button onClick={() => onRemove(item.id)} type="button" title="Remove focus item">
                <X size={10} />
              </button>
            </div>
          ))}
        </div>,
        document.body,
      )}
    </>
  )
}

function ActiveFilterChip({
  label,
  prefix,
  suffix,
  dotColor,
  accentColor,
  dimmed,
  onRemove,
}: {
  label: string
  prefix?: string
  suffix?: string
  dotColor?: string
  accentColor?: string
  dimmed?: boolean
  onRemove: () => void
}) {
  return (
    <span
      className={`ume-active-chip ${dimmed ? 'dimmed' : ''}`}
      style={{
        '--chip-color': dimmed ? 'var(--ume-color-text-muted)' : accentColor || 'var(--ume-color-accent)',
        '--chip-bg': dimmed ? 'transparent' : `${accentColor || 'var(--ume-color-accent)'}10`,
      } as CSSProperties}
    >
      {dotColor && <i style={{ background: dimmed ? '#bbb' : dotColor }} />}
      {prefix && <small>{prefix}</small>}
      {label}
      {suffix && <small>{suffix}</small>}
      <button onClick={onRemove} type="button">
        <X size={10} />
      </button>
    </span>
  )
}
