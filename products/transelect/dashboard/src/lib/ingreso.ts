/**
 * The second ingreso pair of the 30-Sept-2026 `Resumen` layout
 * (`Fecha de ingreso2`, `N Ingreso2`): a plan's re-entry after a rejection,
 * as the source records it. Earlier workbooks have no such columns, so a
 * version published from one cannot say anything about a second ingreso —
 * the drawer must not render "sin segundo ingreso" for those rows.
 */
export const INGRESO_2_FIELDS = ['fecha_ingreso_2', 'numero_ingreso_2'] as const

/**
 * Whether the published version's source had the second ingreso columns.
 *
 * `null` while unknown (the active-version read has not resolved).
 */
export function ingreso2InSource(sourceFields: readonly string[] | null | undefined): boolean | null {
  if (!sourceFields) return null
  return INGRESO_2_FIELDS.some((field) => sourceFields.includes(field))
}
