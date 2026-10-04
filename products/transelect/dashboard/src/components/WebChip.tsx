/**
 * The «web» mark next to a value that came from a dashboard edit.
 *
 * The word carries the meaning, never the colour. `description` is read by
 * assistive technology (and not shown) where the surrounding layout has no
 * room for the provenance as text; `title` is only a pointer-user extra,
 * because a tooltip cannot be reached by keyboard or touch.
 */
export function WebChip({ title, description }: { title?: string; description?: string }) {
  return (
    <span className="web-chip" title={title} data-testid="web-chip">
      web
      {description && <span className="sr-only">{`, ${description}`}</span>}
    </span>
  )
}
