import type { ReactNode } from 'react'
import { WebChip } from './WebChip'

export function Fact({
  label,
  children,
  wide = false,
  web = false,
}: {
  label: string
  children: ReactNode
  wide?: boolean
  /** The value came from a dashboard edit: mark it «web». */
  web?: boolean
}) {
  return (
    <div className={`fact${wide ? ' wide' : ''}`}>
      <dt>{label}</dt>
      <dd>
        {children}
        {web && (
          <>
            {' '}
            <WebChip />
          </>
        )}
      </dd>
    </div>
  )
}
