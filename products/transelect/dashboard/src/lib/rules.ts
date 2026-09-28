/**
 * Plain-language explanations of the named counting rules the API applies.
 *
 * The API reports which rule produced each number as a basis identifier
 * (`estado_resumido_first_row`, `owner_stage_legacy`, …). Those identifiers
 * are the audit trail and must stay reachable, but they are not something an
 * operator should have to decode to read a page. So a page leads with what
 * was found, and the identifier, the source columns and the exact rule sit in
 * an optional «Cómo se calcula» detail (see `ui/HowCalculated.tsx`).
 *
 * This module only describes the rules. It does not compute or change any of
 * them: the wording mirrors `transelec_ingestion/status_rollups.py`,
 * `summary_view.py`, `pending_view.py` and `owner_status_view.py`, and a
 * change to a rule there must be reflected here.
 */

export interface RuleExplanation {
  /** What the rule decides, in a few words. */
  name: string
  /** The exact calculation, in Spanish, naming the source columns. */
  steps: string[]
  /** Source columns of the «Resumen» sheet the rule reads, as headed there. */
  sourceColumns: string[]
}

/**
 * «Predio» throughout the dashboard is one value of the workbook's own
 * `ID_Predo_Unico`, or — when that cell is blank — the combination
 * PMF + Rol + N Predio (`resolve_predio_group_key` in the importer).
 */
export const PREDIO_DEFINITION =
  'Un predio es un valor distinto de «ID_Predo_Unico»; si esa celda está vacía, se usa la combinación PMF + Rol + N Predio de la fila.'

export const RULES: Record<string, RuleExplanation> = {
  estado_resumido_first_row: {
    name: 'Estado de cada PMF según su primera fila',
    steps: [
      'Cada PMF se cuenta una sola vez, aunque tenga varias filas en la hoja «Resumen».',
      'Su estado es el «Estado resumido» de su primera fila (la de número de fila más bajo).',
      'Los conteos por predio usan el mismo criterio: cada predio se cuenta una vez, con el «Estado resumido» de su primera fila.',
    ],
    sourceColumns: ['PMF', 'Estado resumido', 'ID_Predo_Unico'],
  },
  pending_priority_legacy: {
    name: 'PMF pendiente prioritario',
    steps: [
      'Cada PMF se evalúa una sola vez, con su primera fila.',
      'Es pendiente prioritario si en esa fila «N Ingreso» está vacío, o si «Estado» contiene el texto «rechaz» (rechazo, rechazado…).',
      'No usa «Estado resumido», por eso un PMF puede figurar «En trámite» en el Resumen y aun así ser pendiente prioritario.',
    ],
    sourceColumns: ['PMF', 'N Ingreso', 'Estado'],
  },
  pending_stage_legacy: {
    name: 'Etapa del pendiente, deducida del texto de «Estado»',
    steps: [
      'Solo se aplica a los PMF pendientes prioritarios, leyendo «Estado» en su primera fila.',
      'Si contiene «prepar» → «En preparación / no presentado».',
      'Si contiene «recurso» y «rechaz» → «Recurso rechazado».',
      'Cualquier otro texto → «Rechazado». Este grupo también incluye PMF sin N.º de ingreso cuyo estado no menciona preparación ni recurso.',
      'Es una lectura del texto, no una clasificación confirmada por CONAF.',
    ],
    sourceColumns: ['Estado'],
  },
  owner_stage_legacy: {
    name: 'Estado de cada predio en la tabla por propietario',
    steps: [
      'Cada predio se cuenta una sola vez, con su primera fila.',
      'Si «Estado» contiene «rechaz», el predio se cuenta como «Rechazado», diga lo que diga «Estado resumido».',
      'Si no, se usa su «Estado resumido»: «Aprobado» y «En trámite» se cuentan como tales; «Pendiente», «Tachado» o vacío van a «Pend./tach.».',
    ],
    sourceColumns: ['ID_Predo_Unico', 'Tipo de propietario', 'Estado', 'Estado resumido'],
  },
  pmf_from_source_rows: {
    name: 'Seguimiento AEF por PMF',
    steps: [
      'Para cada PMF se reúnen las filas que tienen valor en cada columna de seguimiento.',
      'Si todas esas filas dicen lo mismo, ese es el valor del PMF, indicando de qué filas viene.',
      'Si dicen cosas distintas, el PMF se marca con conflicto y no se elige ningún valor.',
      'Las filas vacías siguen vacías: no se copia el valor a otras filas.',
    ],
    sourceColumns: ['AEF', 'Quien solicita', 'Fecha solicitud', 'Fecha corta', 'Fecha termino'],
  },
}

export function ruleFor(basis: string): RuleExplanation | null {
  return RULES[basis] ?? null
}
