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
  lifecycle_pmf_v1: {
    name: 'Dónde está cada PMF en la tramitación CONAF',
    steps: [
      'Cada PMF se evalúa una sola vez, con su primera fila (la de número de fila más bajo).',
      'El grupo sale de «Estado resumido»: «Aprobado» → Aprobado; «En trámite» o «Rechazado» → En trámite; «Descartado» → Descartado; «Desistido» → Desistido.',
      'Dentro de «En trámite», el paso sale de «Estado»: sin «N Ingreso» ni «N Ingreso2» → Sin ingreso a CONAF; «En evaluación» → En evaluación; «Rechazado» o un recurso rechazado → Rechazado, esperando recurso; «Recurso reposición» → En recurso de reposición; «Recurso jerárquico» → En recurso jerárquico.',
      'Un rechazo no es un final: todo rechazo termina en Aprobado, Descartado o Desistido.',
      'No cuentan mayúsculas, tildes ni espacios; ninguna otra variación se adivina. Un valor que la regla no conoce, o un «Estado» que contradice al «Estado resumido», deja el PMF «Sin clasificar» con el motivo, y se lista en Calidad.',
      'Si las filas del PMF no tienen el mismo estado, se usa la primera y el PMF se marca para revisar.',
      'Categorías provisionales hasta que Campo Digital confirme el vocabulario.',
    ],
    sourceColumns: ['PMF', 'Estado resumido', 'Estado', 'N Ingreso', 'N Ingreso2', 'Tipo de rechazo'],
  },
  plazo_conaf_90_habiles_v1: {
    name: 'Plazo CONAF de 90 días hábiles',
    steps: [
      'Para cada PMF, la fecha de inicio es «Fecha de ingreso2» si la tiene; si no, «Fecha de ingreso1». Un reingreso vuelve a contar el plazo.',
      'Si la fecha más reciente no se puede leer, no se usa la anterior: el PMF queda «Sin fecha legible».',
      'Las fechas se leen en todas las filas del PMF; si las filas traen fechas distintas, no se elige ninguna («Fechas distintas»).',
      'El día 1 es el primer día hábil después del ingreso; el plazo vence el día hábil 90. Son hábiles los días de lunes a viernes que no son feriados nacionales de Chile. Los feriados regionales no se descuentan.',
      '«Hoy» es la fecha del servidor en Chile, no la del navegador ni la columna «Hoy» de la planilla.',
      'Vencido si hoy es posterior al vencimiento; por vencer si quedan 10 días hábiles o menos; los PMF Aprobados, Descartados o Desistidos no aplican.',
      'La columna «90 dias» de la planilla se compara con este cálculo; nunca se reemplaza.',
      'Regla provisional hasta que Campo Digital confirme cuándo empieza el plazo y si se suspende.',
    ],
    sourceColumns: ['PMF', 'Fecha de ingreso2', 'Fecha de ingreso1', '90 dias', 'Estado resumido'],
  },
  vencimiento_columna_90_dias_legacy: {
    name: 'Ingresos sobre 90 días, regla anterior',
    steps: [
      'Fila por fila: «Estado resumido» distinto de «Aprobado» y fecha «90 dias» de la planilla anterior a hoy.',
      'Usa la fecha que trae la planilla, sin contar días hábiles. Se muestra solo para comparar con el plazo calculado.',
    ],
    sourceColumns: ['Estado resumido', '90 dias'],
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
