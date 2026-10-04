/** The «web» mark next to a value that came from a dashboard edit. */
export function WebChip({ title }: { title?: string }) {
  return (
    <span className="web-chip" title={title} data-testid="web-chip">
      web
    </span>
  )
}
