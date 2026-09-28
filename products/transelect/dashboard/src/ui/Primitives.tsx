/**
 * The small shared pieces: section headers, figures, stat strips, chips and
 * the disclosure.
 *
 * These carry no product knowledge. They exist so that a heading, a number or
 * a reference count looks and behaves identically in five sections without
 * five near-copies of the same markup, which is what produced the shipped
 * page's interchangeable-card problem.
 */
import type { ReactNode } from 'react'
import { useId, useState } from 'react'

/**
 * A section heading and a right-hand slot.
 *
 * The heading no longer carries the API's rule identifier: a section that
 * rests on a named rule ends with a «Cómo se calcula» detail
 * (`ui/HowCalculated.tsx`) that explains it and names it exactly.
 */
export function SectionHeader({
  title,
  id,
  meta,
  actions,
}: {
  title: ReactNode
  id?: string
  meta?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="section-head">
      <h2 id={id}>
        {title}
      </h2>
      {(meta || actions) && (
        <div className="section-head-meta">
          {meta}
          {actions}
        </div>
      )}
    </div>
  )
}

/**
 * One number a section leads with.
 *
 * Proportional figures, deliberately: a large standalone number reads better
 * when its digits keep their natural widths. Columns of numbers get
 * `tabular-nums` instead, so they align.
 */
export function Figure({
  value,
  unit,
  label,
  note,
  lead = false,
  testId,
}: {
  value: string
  unit?: string
  label: string
  note?: ReactNode
  lead?: boolean
  testId?: string
}) {
  return (
    <div className={`figure${lead ? ' lead' : ''}`}>
      <div className="figure-value">
        <span data-testid={testId}>{value}</span>
        {unit && <span className="unit">{unit}</span>}
      </div>
      <div className="figure-label">{label}</div>
      {note && <div className="figure-note">{note}</div>}
    </div>
  )
}

export interface StatItem {
  id: string
  label: string
  value: string
  sub: string
}

/**
 * Reference counts, as a rule-separated strip.
 *
 * These are numbers a reader looks *up*; they are deliberately quieter than
 * the attention row, which carries numbers that mean somebody has work to do.
 * In the shipped interface both groups were eight identical cards, so
 * "Roles" shouted exactly as loudly as "Pendientes prioritarios".
 */
export function StatStrip({ items, testId }: { items: StatItem[]; testId?: string }) {
  return (
    <div className="stat-strip" data-testid={testId}>
      {items.map((item) => (
        <div className="stat" key={item.id} data-stat={item.id}>
          <span className="stat-label">{item.label}</span>
          <span className="stat-value" data-testid={`kpi-${item.id}`}>
            {item.value}
          </span>
          <span className="stat-sub">{item.sub}</span>
        </div>
      ))}
    </div>
  )
}

/** A dismissible label describing one active filter. */
export function Chip({
  children,
  onRemove,
  removeLabel,
}: {
  children: ReactNode
  onRemove?: () => void
  removeLabel?: string
}) {
  return (
    <span className="chip">
      {children}
      {onRemove && (
        <button
          type="button"
          className="chip-remove"
          aria-label={removeLabel}
          onClick={onRemove}
        >
          ×
        </button>
      )}
    </span>
  )
}

/**
 * A panel that expands in place.
 *
 * The height animation uses `grid-template-rows: 0fr -> 1fr` so the panel
 * animates to its own natural height without a measured pixel value, and so
 * nothing below it jumps when the content inside changes size.
 */
export function Disclosure({
  open,
  id,
  children,
}: {
  open: boolean
  id: string
  children: ReactNode
}) {
  return (
    <div
      className={`disclosure-panel${open ? ' open' : ''}`}
      id={id}
      // `inert` rather than `hidden`: the panel must stay in the layout to
      // animate, but nothing inside a closed one may be tabbed to, clicked,
      // or read out.
      inert={!open}
    >
      <div className="disclosure-inner">{children}</div>
    </div>
  )
}

/**
 * A labelled group whose contents can be toggled from a trigger elsewhere.
 * Returns the trigger props so the caller can render its own button.
 */
export function useDisclosure(initial = false) {
  const [open, setOpen] = useState(initial)
  const id = useId()
  return {
    open,
    id,
    toggle: () => setOpen((value) => !value),
    close: () => setOpen(false),
    triggerProps: { 'aria-expanded': open, 'aria-controls': id },
  }
}
