/**
 * «Cómo se calcula» — the audit detail behind a number, closed by default.
 *
 * A page states what was found in plain Spanish. This disclosure carries what
 * an auditor needs to reproduce it: the rule in steps, the source columns it
 * reads, and the identifier the API reported for it. It is a native
 * `<details>`, so it works with the keyboard and a screen reader with no
 * script, prints when opened, and never hides the number itself.
 */
import type { ReactNode } from 'react'
import { ruleFor } from '../lib/rules'

export function HowCalculated({
  bases,
  children,
  testId,
  summary = 'Cómo se calcula',
}: {
  /** API basis identifiers behind the figure, in the order they matter. */
  bases?: readonly string[]
  /** Extra, context-specific detail shown before the rules. */
  children?: ReactNode
  testId?: string
  summary?: string
}) {
  const rules = (bases ?? []).map((basis) => ({ basis, rule: ruleFor(basis) }))

  return (
    <details className="how" data-testid={testId}>
      <summary>{summary}</summary>
      <div className="how-body">
        {children}
        {rules.map(({ basis, rule }) => (
          <div className="how-rule" key={basis}>
            {rule ? (
              <>
                <p className="how-rule-name">{rule.name}</p>
                <ol>
                  {rule.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
                <p className="how-meta">
                  Columnas de la hoja «Resumen»:{' '}
                  {rule.sourceColumns.map((column, index) => (
                    <span key={column}>
                      {index > 0 && ', '}
                      <span className="source-col" translate="no">
                        {column}
                      </span>
                    </span>
                  ))}
                </p>
              </>
            ) : null}
            <p className="how-meta">
              Regla informada por la API:{' '}
              <code className="basis-tag" translate="no">
                {basis}
              </code>
            </p>
          </div>
        ))}
      </div>
    </details>
  )
}
