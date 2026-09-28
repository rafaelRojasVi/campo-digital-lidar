/**
 * Part-to-whole, as a horizontal stacked bar.
 *
 * This replaces three separate blocks from the shipped interface: the two
 * conic-gradient donuts (TR-FUNC-009/010) and the five-tile status hero
 * (TR-FUNC-011). Every value those blocks showed is still shown, and still
 * comes from `GET /transelec/summary` under the current filter state —
 * nothing here computes a business number.
 *
 * Why the form changed. The donuts compared two percentages under two points
 * apart (68,75 % against 67,92 % in the reviewed version), which is the case
 * the data-visualisation reference names as a donut anti-pattern: reading
 * either arc is strictly harder than reading the number already printed
 * beside it. The status hero then restated the same predio-grain composition
 * a second time, in a second card, in a different form. One bar per grain
 * answers both questions in one place, and puts the two grains on the same
 * baseline so the reader can actually compare them.
 *
 * Identity never rests on colour alone, which is what makes the palette's
 * colour-vision warning safe to carry:
 *
 *  - a 2px gap in the surface colour separates touching segments (a gap, not
 *    a border drawn around each mark);
 *  - a legend is present whenever there is more than one segment, and names
 *    every segment with its own count;
 *  - segments wide enough to hold one carry a direct label;
 *  - the same numbers appear as text in the legend and in the tables, so a
 *    reader who sees no colour at all loses nothing.
 */
import { formatInteger, formatNumber } from '../format'

export type SegmentTone = 'approved' | 'progress' | 'late' | 'struck' | 'none'

export interface CompositionSegment {
  key: string
  label: string
  value: number
  tone: SegmentTone
}

/** A segment gets an inline label only when it is wide enough to hold one. */
const DIRECT_LABEL_MIN_PERCENT = 9

export function CompositionBar({
  title,
  noun,
  segments,
  testId,
  lead: showLead = true,
}: {
  /**
   * Omitted when the enclosing section heading already names this bar —
   * repeating it directly above the track is the same duplication this
   * component exists to remove.
   */
  title?: string
  /** The unit being counted, for the accessible description and the readout. */
  noun: string
  segments: CompositionSegment[]
  testId?: string
  /**
   * Whether the first segment is the one the bar is *about*.
   *
   * True for an approval bar, where "108 of 159 approved" is the headline.
   * False for a bar whose segments are peers — the three pending stages, for
   * instance, where singling the first one out would invent an emphasis the
   * data does not carry. The legend then does all the work.
   */
  lead?: boolean
}) {
  const present = segments.filter((segment) => segment.value > 0)
  const total = segments.reduce((sum, segment) => sum + segment.value, 0)
  const lead = segments[0]
  const leadPercentage = total ? (lead.value / total) * 100 : 0

  const description = present
    .map((segment) => `${formatInteger(segment.value)} ${segment.label}`)
    .join(', ')

  return (
    <div className="composition" data-testid={testId}>
      <div className="composition-head">
        {title && <span className="composition-title">{title}</span>}
        <span className="composition-total" data-testid={testId && `${testId}-total`}>
          {showLead
            ? `${formatInteger(lead.value)} de ${formatInteger(total)} ${noun}`
            : `${formatInteger(total)} ${noun}`}
        </span>
      </div>

      <div
        className="composition-track"
        role="img"
        aria-label={`${title ? `${title}: ` : ''}${description || `sin ${noun}`}. Total ${formatInteger(total)}.`}
      >
        {present.map((segment) => {
          const percentage = total ? (segment.value / total) * 100 : 0
          return (
            <div
              key={segment.key}
              className="composition-seg"
              data-tone={segment.tone}
              data-segment={segment.key}
              style={{ width: `${percentage}%` }}
            >
              {percentage >= DIRECT_LABEL_MIN_PERCENT && formatInteger(segment.value)}
            </div>
          )
        })}
        {total === 0 && (
          <div className="composition-seg" data-tone="none" style={{ width: '100%' }} />
        )}
      </div>

      {segments.length > 1 && (
        <div className="composition-legend">
          {segments.map((segment) => (
            <span key={segment.key}>
              <i className="legend-swatch" data-tone={segment.tone} aria-hidden="true" />
              {segment.label} <b data-testid={testId && `${testId}-${segment.key}`}>
                {formatInteger(segment.value)}
              </b>
            </span>
          ))}
          {showLead && (
            <span className="muted">
              {formatNumber(leadPercentage)}% {lead.label.toLocaleLowerCase('es-CL')}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

/** The percentage a composition's first segment represents, for a figure. */
export function leadPercentage(segments: CompositionSegment[]): number {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0)
  return total ? (segments[0].value / total) * 100 : 0
}
