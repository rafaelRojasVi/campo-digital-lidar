/**
 * TR-FUNC-042 — the "Consulta documental" explanation.
 *
 * The wording is the source dashboards' own, which are identical here.
 *
 * What changed is its rank. In the shipped interface this was a full-width
 * amber block pinned above every other thing on the page, permanently — the
 * page's strongest alert treatment spent on a static sentence that is true
 * of every version and never changes. It is what it always was: a hint about
 * how the search field behaves. So it renders as a hint, directly under the
 * field it describes.
 */
export function NoticeBanner() {
  return (
    <p className="notice no-print" data-testid="notice-banner">
      <b>Consulta documental:</b> el campo <b>N.º de ingreso está asociado directamente a cada
      PMF</b>. Escriba el número completo o una parte en «Búsqueda general» para obtener el PMF,
      rol, predio y estado correspondiente. La base no incluye un campo separado de N.º de
      resolución.
    </p>
  )
}
