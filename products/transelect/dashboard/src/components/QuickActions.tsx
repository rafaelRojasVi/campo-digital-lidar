/**
 * TR-FUNC-024-031 — the eight "Preguntas frecuentes", redistributed.
 *
 * The shipped interface answered all eight with eight identical cards in the
 * middle of the dashboard, three of which demonstrably under-delivered on
 * their own question: a lookup that only focused a search box, a "superficie"
 * card that only scrolled, a "cada empresa" card that only opened a dropdown.
 * The parity matrix's disposition for all three is "implement (as designed)":
 * reproduce the current behaviour and say plainly what it does, rather than
 * silently inventing a comparison view nobody asked for.
 *
 * Reproducing the behaviour is not the same as reproducing the card grid. The
 * four questions that are genuinely *filter presets* live here, on the
 * Explorador, next to the filters they set. The other four were never really
 * shortcuts at all and now have real homes:
 *
 *   024 ¿Qué falta presentar a CONAF?  Resumen attention card → Pendientes
 *   025 ¿A qué PMF corresponde un N.º de ingreso?
 *                                      the Explorador's own search field
 *   027 ¿Cuál es la superficie de corta?
 *                                      the Resumen's scale strip
 *   031 ¿Qué ingresos superaron 90 días?
 *                                      the Pendientes toggle
 *
 * Every preset below still starts from a clean filter state, exactly as the
 * source's `quick()` did by calling `resetFilters()` before each branch.
 */

export type QuickActionType = 'easement' | 'rejected' | 'legal' | 'company'

interface QuickActionCard {
  type: QuickActionType
  title: string
  sub: string
}

export const EASEMENT_VALUE = 'Servidumbre firmada'

export const QUICK_ACTIONS: QuickActionCard[] = [
  {
    type: 'easement',
    title: '¿Cuáles tienen servidumbre?',
    sub: 'Filtra «Servidumbre firmada».',
  },
  {
    type: 'rejected',
    title: '¿Qué expedientes tienen rechazo?',
    sub: 'Busca «rechaz» en todos los campos, no sólo en Estado.',
  },
  {
    type: 'legal',
    title: '¿Dónde está el principal cuello de botella?',
    sub: 'Busca «legal» en todos los campos, no sólo en Estado.',
  },
  {
    type: 'company',
    title: '¿Cómo avanza cada empresa?',
    sub: 'Abre el filtro Empresa; no existe todavía una tabla comparativa por empresa.',
  },
]

export function QuickActions({ onQuick }: { onQuick: (type: QuickActionType) => void }) {
  return (
    <section className="questions no-print" aria-labelledby="faq-title">
      <h2 id="faq-title" className="eyebrow" style={{ marginBottom: 'var(--s-3)' }}>
        Consultas frecuentes
      </h2>
      {/*
        Each preset states what it does directly underneath itself. The
        shipped grid put eight of these in identical cards and left three of
        them promising more than they delivered; the copy here is the parity
        matrix's own wording, kept honest and kept next to its control.
      */}
      <div className="presets">
        {QUICK_ACTIONS.map((card) => (
          <div className="preset" key={card.type}>
            <button
              type="button"
              className="btn alt small"
              data-quick={card.type}
              onClick={() => onQuick(card.type)}
            >
              {card.title}
            </button>
            <span>{card.sub}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
