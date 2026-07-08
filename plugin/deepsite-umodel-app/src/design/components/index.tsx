import React, {
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';
import { X } from 'lucide-react';
import { t } from '@grafana/i18n';
import '../components.css';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle';
type ControlSize = 'sm' | 'md';

export function Button({
  variant = 'secondary',
  size = 'md',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ControlSize }) {
  return <button className={`om-button ${variant} ${size} ${className}`} {...props} />;
}

export function IconButton({
  label,
  variant = 'ghost',
  size = 'md',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; variant?: ButtonVariant; size?: ControlSize }) {
  return (
    <button
      className={`om-button ${variant} ${size} om-icon-button ${className}`}
      aria-label={label}
      title={label}
      {...props}
    />
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="om-field">
      <span className="om-label">{label}</span>
      {children}
    </label>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="om-input" {...props} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className="om-textarea" {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className="om-select" {...props} />;
}

export function JsonEditor({
  value,
  onChange,
  minHeight = 260,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  minHeight?: number;
  placeholder?: string;
}) {
  return (
    <textarea
      className="om-textarea om-json"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      spellCheck={false}
      style={{ minHeight }}
    />
  );
}

export function Panel({
  title,
  action,
  children,
  className = '',
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`om-panel ${className}`}>
      {(title || action) && (
        <div className="om-panel-header">
          <div>{title}</div>
          <div>{action}</div>
        </div>
      )}
      <div className="om-panel-body">{children}</div>
    </section>
  );
}

export function Badge({
  tone = 'default',
  children,
}: {
  tone?: 'default' | 'success' | 'warning' | 'danger' | 'indigo';
  children: ReactNode;
}) {
  return <span className={`om-badge ${tone}`}>{children}</span>;
}

export function StatusDot({ status }: { status?: 'ok' | 'warn' | 'bad' }) {
  return <span className={`om-status-dot ${status || ''}`} />;
}

export function Tabs<T extends string>({
  value,
  items,
  onChange,
}: {
  value: T;
  items: Array<{ value: T; label: ReactNode; icon?: ReactNode }>;
  onChange: (value: T) => void;
}) {
  return (
    <div className="om-tabs">
      {items.map((item) => (
        <button
          key={item.value}
          className={`om-tab ${item.value === value ? 'active' : ''}`}
          onClick={() => onChange(item.value)}
          type="button"
        >
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  );
}

export function SegmentedControl<T extends string>({
  value,
  items,
  onChange,
  size = 'md',
  className = '',
}: {
  value: T;
  items: Array<{ value: T; label: ReactNode; icon?: ReactNode; disabled?: boolean }>;
  onChange: (value: T) => void;
  size?: ControlSize;
  className?: string;
}) {
  return (
    <div className={`om-segmented ${size} ${className}`}>
      {items.map((item) => (
        <button
          key={item.value}
          className={item.value === value ? 'active' : ''}
          disabled={item.disabled}
          onClick={() => onChange(item.value)}
          type="button"
        >
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  );
}

export function EmptyState({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="om-empty">
      <div>
        <div style={{ fontWeight: 700, color: 'var(--om-text)', marginBottom: 6 }}>{title}</div>
        {detail && <div style={{ fontSize: 13, marginBottom: action ? 14 : 0 }}>{detail}</div>}
        {action}
      </div>
    </div>
  );
}

export function Modal({
  title,
  children,
  footer,
  onClose,
}: {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="om-modal-backdrop" role="presentation">
      <div className="om-modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="om-panel-header">
          <strong>{title}</strong>
          <IconButton label={t('common.close', 'Close')} onClick={onClose}>
            <X size={16} />
          </IconButton>
        </div>
        <div className="om-modal-body om-panel-body">{children}</div>
        {footer && (
          <div className="om-panel-header" style={{ borderBottom: 0, borderTop: '1px solid var(--om-border)' }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
