/**
 * «Versiones»: every version of the Rodales layer, where each came from, who
 * loaded it, and the audited trail of what the map showed and when.
 *
 * Viewers see the versions that have been published at some point; the
 * pending uploads are for the people who review them. Restoring an earlier
 * version goes through its review page, the same place as «Publicar».
 */
import { useEffect, useState } from 'react'
import { canUpload, fetchVersions } from '../api.ts'
import { Notice, PageShell, StatusChip } from '../components/PageShell.tsx'
import { formatHa, formatInt } from '../lib/format.ts'
import { EVENT_LABELS, formatDateTime, versionSource } from '../lib/versions.ts'
import { ROUTES, mapPath, onLinkClick, reviewPath } from '../router.ts'
import type { ForestryRole, VersionsResponse } from '../types.ts'

type Phase =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; data: VersionsResponse }

export function VersionesPage({
  role,
  search,
}: {
  role: ForestryRole | null
  search: URLSearchParams
}) {
  const [phase, setPhase] = useState<Phase>({ status: 'loading' })
  const [reload, setReload] = useState(0)
  const uploader = canUpload(role)
  const published = search.get('publicada')
  const restored = search.get('restaurada')

  useEffect(() => {
    let cancelled = false
    fetchVersions()
      .then((data) => {
        if (!cancelled) setPhase({ status: 'ready', data })
      })
      .catch(() => {
        if (!cancelled) setPhase({ status: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [reload])

  return (
    <PageShell active={ROUTES.versiones} role={role}>
      <div className="page__heading">
        <h2 className="page__title">Versiones de la capa de rodales</h2>
        {uploader ? (
          <a
            className="button"
            href={ROUTES.importar}
            onClick={(event) => onLinkClick(event, ROUTES.importar)}
          >
            Cargar versión
          </a>
        ) : null}
      </div>
      <p className="page__lead">
        El mapa muestra siempre la versión publicada. Cargar una versión no la publica; publicar y
        restaurar quedan registrados con el nombre de quien lo hizo.
      </p>

      {published !== null ? (
        <Notice tone="success" title={`Versión N.º ${published} publicada`}>
          Todos los usuarios de Rodales ven ahora esta versión en el mapa.
        </Notice>
      ) : null}
      {restored !== null ? (
        <Notice tone="success" title={`Versión N.º ${restored} restaurada`}>
          Todos los usuarios de Rodales ven de nuevo esta versión en el mapa.
        </Notice>
      ) : null}

      {phase.status === 'loading' ? (
        <p className="page__busy" role="status">
          Cargando versiones…
        </p>
      ) : phase.status === 'error' ? (
        <Notice tone="error" title="No fue posible cargar las versiones">
          <button type="button" className="button button--ghost" onClick={() => {
              setPhase({ status: 'loading' })
              setReload((n) => n + 1)
            }}>
            Reintentar
          </button>
        </Notice>
      ) : phase.data.versions.length === 0 ? (
        <Notice tone="info" title="Todavía no hay versiones">
          {uploader
            ? 'Cargue la primera capa de rodales para revisarla y publicarla.'
            : 'Un administrador de Rodales todavía no ha publicado ninguna versión.'}
        </Notice>
      ) : (
        <>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Versión</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Origen</th>
                  <th scope="col">Cargada por</th>
                  <th scope="col" className="numeric">
                    Polígonos
                  </th>
                  <th scope="col" className="numeric">
                    Sup_ha
                  </th>
                  <th scope="col">
                    <span className="visually-hidden">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {phase.data.versions.map((version) => {
                  const source = versionSource(version)
                  const id = version.shapefile_snapshot_id
                  return (
                    <tr key={id}>
                      <td>N.º {id}</td>
                      <td>
                        <StatusChip status={version.status} />
                      </td>
                      <td>
                        {source?.filename ?? version.layer_name}
                        {version.geometry_invalid_count > 0 ? (
                          <p className="muted">
                            {formatInt(version.geometry_invalid_count)} geometrías inválidas
                          </p>
                        ) : null}
                      </td>
                      <td>
                        {source?.by ?? 'Sin registro'}
                        {source !== null ? <p className="muted">{formatDateTime(source.at)}</p> : null}
                      </td>
                      <td className="numeric">{formatInt(version.feature_count)}</td>
                      <td className="numeric">{formatHa(version.total_sup_ha)}</td>
                      <td className="row-actions">
                        <a href={mapPath(id)} onClick={(event) => onLinkClick(event, mapPath(id))}>
                          Ver en el mapa
                        </a>
                        {uploader ? (
                          <a href={reviewPath(id)} onClick={(event) => onLinkClick(event, reviewPath(id))}>
                            {version.status === 'pending'
                              ? 'Revisar y publicar'
                              : version.status === 'previously_published'
                                ? 'Revisar y restaurar'
                                : 'Ver revisión'}
                          </a>
                        ) : null}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <section className="page__section" aria-labelledby="historial">
            <h3 id="historial" className="page__section-title">
              Historial de publicación
            </h3>
            {phase.data.events.length === 0 ? (
              <p>Todavía no se ha publicado ninguna versión.</p>
            ) : (
              <ol className="event-list">
                {phase.data.events.map((event) => (
                  <li key={event.publication_event_id}>
                    <b>{EVENT_LABELS[event.event_type]}</b> de la versión N.º{' '}
                    {event.shapefile_snapshot_id}
                    {event.previous_snapshot_id !== null
                      ? ` (antes se mostraba la N.º ${event.previous_snapshot_id})`
                      : ''}
                    <span className="muted">
                      {' '}
                      · {formatDateTime(event.occurred_at)} ·{' '}
                      {event.actor_display_name ?? 'sin usuario (carga inicial)'}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </PageShell>
  )
}
