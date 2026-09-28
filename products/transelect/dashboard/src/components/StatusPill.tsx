import { cell } from '../format'

const TONES: Record<string, string> = {
  aprobado: 'pill-aprobado',
  'en tramite': 'pill-en-tramite',
  'en trámite': 'pill-en-tramite',
  pendiente: 'pill-pendiente',
  tachado: 'pill-tachado',
}

/**
 * A closed-vocabulary `Estado resumido` badge.
 *
 * The value is rendered as text by React's normal escaping — like every
 * other workbook-derived value in this application, it is untrusted,
 * client-controlled content and never reaches `dangerouslySetInnerHTML`.
 * An unrecognised value still renders, in the neutral tone, rather than
 * disappearing.
 */
export function StatusPill({ value }: { value: string | null }) {
  const text = cell(value)
  if (text === '') return <span className="hint">—</span>
  const tone = TONES[text.toLocaleLowerCase('es-CL')] ?? 'pill-otro'
  return <span className={`pill ${tone}`}>{text}</span>
}
