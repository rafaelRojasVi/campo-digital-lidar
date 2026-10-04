import type { ReactNode } from 'react'

export function Fact({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`fact${wide ? ' wide' : ''}`}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}
