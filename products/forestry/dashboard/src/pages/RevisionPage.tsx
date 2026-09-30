/**
 * «Revisión»: everything to judge a version before «Publicar» (or before
 * «Restaurar» an earlier one): where it came from, how many polygons and
 * hectares, its CRS, its invalid geometries, and what changed against the
 * version the map shows today.
 *
 * The comparison is geometric (apps/api/app/forestry_comparison.py): only an
 * identical geometry is a certain match; OBJECTID and the rodal code are
 * shown as references, never used to pair polygons. Nothing on this page
 * says a rodal was cut.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  ApiError,
  canUpload,
  fetchReview,
  mutationMessage,
  publishSnapshot,
  restoreSnapshot,
} from '../api.ts'
import { ConfirmDialog } from '../components/ConfirmDialog.tsx'
import { Notice, PageShell, StatusChip } from '../components/PageShell.tsx'
import { formatHa, formatInt, shortFingerprint, sourceUnitsToHa } from '../lib/format.ts'
import { qualityFlagLabel } from '../lib/qualityLabels.ts'
import {
  CHANGE_DESCRIPTIONS,
  CHANGE_LABELS,
  formatBytes,
  formatDateTime,
  versionSource,
} from '../lib/versions.ts'
import { ROUTES, mapPath, navigate, onLinkClick } from '../router.ts'
import type { ChangeItem, ChangeKind, FeatureRef, ForestryRole, Review, Version } from '../types.ts'

const KIND_ORDER: ChangeKind[] = ['uncertain', 'geometry_changed', 'removed', 'added', 'same_geometry']
const ITEMS_SHOWN = 50

type Phase =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; review: Review }

function signed(value: number, format: (n: number) => string): string {
  if (value === 0) return 'sin cambio'
  return `${value > 0 ? '+' : '−'}${format(Math.abs(value))}`
}

function refLabel(ref: FeatureRef): string {
  const predio = ref.nom_predio ?? ref.cod_predial ?? 'predio sin nombre'
  const rodal = ref.n_rodal === null ? 'rodal en blanco' : `rodal ${ref.n_rodal}`
  return `${predio}, ${rodal}`
}

function RefList({ refs }: { refs: FeatureRef[] }) {
  if (refs.length === 0) return <span className="muted">Ninguno</span>
  return (
    <ul className="ref-list">
      {refs.map((ref) => (
        <li key={ref.feature_ordinal}>
          {refLabel(ref)}
          <span className="muted">
            {' '}
            · N.º {ref.feature_ordinal} · OBJECTID {ref.source_objectid ?? 'vacío'} ·{' '}
            {formatHa(sourceUnitsToHa(ref.geometry_area_source_units))} ha
          </span>
        </li>
      ))}
    </ul>
  )
}

function ChangeRow({ item }: { item: ChangeItem }) {
  const largest = item.overlaps.reduce((max, o) => Math.max(max, o.overlap_ratio_of_smaller), 0)
  return (
    <tr>
      <td>
        <span className={`change-kind change-kind--${item.kind}`}>{CHANGE_LABELS[item.kind]}</span>
      </td>
      <td>
        <RefList refs={item.published} />
      </td>
      <td>
        <RefList refs={item.pending} />
      </td>
      <td>
        {item.changed_fields.length > 0 ? (
          <span>{item.changed_fields.join(', ')}</span>
        ) : item.overlaps.length > 0 ? (
          <span className="muted">
            Superposición de hasta {Math.round(largest * 100)} % del polígono menor
          </span>
        ) : (
          <span className="muted">Sin superposición</span>
        )}
        {item.same_objectid === false ? (
          <p className="muted">El OBJECTID cambió; no se usa para emparejar.</p>
        ) : null}
      </td>
    </tr>
  )
}

function ChangeGroup({ kind, items }: { kind: ChangeKind; items: ChangeItem[] }) {
  const [expanded, setExpanded] = useState(false)
  if (items.length === 0) return null
  const shown = expanded ? items : items.slice(0, ITEMS_SHOWN)
  return (
    <section className="change-group" aria-labelledby={`change-${kind}`}>
      <h4 id={`change-${kind}`} className="change-group__title">
        {CHANGE_LABELS[kind]} ({formatInt(items.length)})
      </h4>
      <p className="change-group__description">{CHANGE_DESCRIPTIONS[kind]}</p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Cambio</th>
              <th scope="col">Versión publicada</th>
              <th scope="col">Esta versión</th>
              <th scope="col">Detalle</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((item, index) => (
              <ChangeRow key={index} item={item} />
            ))}
          </tbody>
        </table>
      </div>
      {items.length > ITEMS_SHOWN ? (
        <button type="button" className="button button--ghost" onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Mostrar menos' : `Mostrar los ${formatInt(items.length)}`}
        </button>
      ) : null}
    </section>
  )
}

function SourceDetails({ version }: { version: Version }) {
  const source = versionSource(version)
  const upload = version.uploads.at(-1)
  return (
    <dl className="facts">
      <div>
        <dt>Archivo</dt>
        <dd>{source?.filename ?? 'Sin registro'}</dd>
      </div>
      <div>
        <dt>Cargado por</dt>
        <dd>{source?.by ?? 'Sin registro'}</dd>
      </div>
      <div>
        <dt>Fecha de carga</dt>
        <dd>{source !== null ? formatDateTime(source.at) : 'Sin registro'}</dd>
      </div>
      {upload !== undefined ? (
        <div>
          <dt>Tamaño</dt>
          <dd>{formatBytes(upload.byte_size)}</dd>
        </div>
      ) : null}
      <div>
        <dt>Capa</dt>
        <dd>{version.layer_name}</dd>
      </div>
      <div>
        <dt>Sistema de coordenadas</dt>
        <dd>
          {version.crs_name ?? 'Declarado'} (EPSG:{version.storage_srid})
        </dd>
      </div>
      <div>
        <dt>Huella del contenido</dt>
        <dd>
          <code title={version.family_fingerprint}>{shortFingerprint(version.family_fingerprint)}</code>
        </dd>
      </div>
      {version.uploads.length > 1 ? (
        <div>
          <dt>Cargas del mismo contenido</dt>
          <dd>{version.uploads.length}</dd>
        </div>
      ) : null}
    </dl>
  )
}

export function RevisionPage({
  role,
  versionId,
  uploadStatus,
}: {
  role: ForestryRole | null
  versionId: number | null
  uploadStatus: string | null
}) {
  const [phase, setPhase] = useState<Phase>(
    versionId === null
      ? { status: 'error', message: 'Falta el número de versión a revisar.' }
      : { status: 'loading' },
  )
  const [reload, setReload] = useState(0)
  const [acknowledged, setAcknowledged] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    if (versionId === null) return
    let cancelled = false
    fetchReview(versionId)
      .then((review) => {
        if (!cancelled) setPhase({ status: 'ready', review })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const message =
          error instanceof ApiError && error.status === 404
            ? 'No se encontró la versión solicitada.'
            : error instanceof ApiError && error.status === 403
              ? 'Su cuenta no puede revisar versiones de Rodales.'
              : 'No fue posible cargar la revisión. Reintente.'
        setPhase({ status: 'error', message })
      })
    return () => {
      cancelled = true
    }
  }, [versionId, reload])

  const refresh = useCallback(() => {
    setPhase({ status: 'loading' })
    setActionError(null)
    setAcknowledged(false)
    setReload((n) => n + 1)
  }, [])

  if (phase.status !== 'ready') {
    return (
      <PageShell active={ROUTES.versiones} role={role}>
        {phase.status === 'loading' ? (
          <p className="page__busy" role="status">
            Preparando la revisión: se compara cada polígono con la versión publicada…
          </p>
        ) : (
          <Notice tone="error" title="Revisión no disponible">
            <p>{phase.message}</p>
            <p>
              <a href={ROUTES.versiones} onClick={(event) => onLinkClick(event, ROUTES.versiones)}>
                Volver a Versiones
              </a>
            </p>
          </Notice>
        )}
      </PageShell>
    )
  }

  const { review } = phase
  const { version, published_version: published, comparison } = review
  const action = review.can_publish ? 'publish' : review.can_restore ? 'restore' : null
  const mayAct = canUpload(role) && action !== null
  const needsAcknowledgement = action === 'publish' && review.review_required
  const expected = published?.shapefile_snapshot_id ?? null

  const activate = async () => {
    setBusy(true)
    setActionError(null)
    try {
      if (action === 'publish') {
        await publishSnapshot(version.shapefile_snapshot_id, expected, acknowledged)
      } else {
        await restoreSnapshot(version.shapefile_snapshot_id, expected)
      }
      navigate(`${ROUTES.versiones}?${action === 'publish' ? 'publicada' : 'restaurada'}=${version.shapefile_snapshot_id}`)
    } catch (error) {
      setActionError(
        mutationMessage(error, 'No se pudo completar la acción. La versión publicada no cambió.'),
      )
      setBusy(false)
      setConfirming(false)
    }
  }

  const byKind = (kind: ChangeKind) => comparison?.items.filter((item) => item.kind === kind) ?? []

  return (
    <PageShell active={ROUTES.versiones} role={role}>
      <div className="page__heading">
        <h2 className="page__title">Revisión de la versión N.º {version.shapefile_snapshot_id}</h2>
        <StatusChip status={version.status} />
      </div>

      {uploadStatus === 'uploaded' ? (
        <Notice tone="success" title="Archivo cargado">
          La versión quedó pendiente de revisión. El mapa publicado no cambió.
        </Notice>
      ) : uploadStatus === 'already_uploaded' ? (
        <Notice tone="info" title="Este contenido ya estaba cargado">
          La capa es idéntica a la versión N.º {version.shapefile_snapshot_id}; no se creó una
          versión nueva. Se registró su carga en el historial.
        </Notice>
      ) : null}

      <p className="page__lead">
        <a
          href={mapPath(version.shapefile_snapshot_id)}
          onClick={(event) => onLinkClick(event, mapPath(version.shapefile_snapshot_id))}
        >
          Ver esta versión en el mapa
        </a>{' '}
        (sólo para usted; no cambia lo que ven los demás).
      </p>

      <section className="page__section" aria-labelledby="origen">
        <h3 id="origen" className="page__section-title">
          Origen
        </h3>
        <SourceDetails version={version} />
      </section>

      <section className="page__section" aria-labelledby="resumen">
        <h3 id="resumen" className="page__section-title">
          Resumen
        </h3>
        <dl className="kpi-row">
          <div>
            <dt>Polígonos</dt>
            <dd>{formatInt(version.feature_count)}</dd>
            {published !== null ? (
              <p className="muted">
                {signed(version.feature_count - published.feature_count, formatInt)} frente a la
                publicada
              </p>
            ) : null}
          </div>
          <div>
            <dt>Superficie (Sup_ha)</dt>
            <dd>{formatHa(version.total_sup_ha)} ha</dd>
            {published !== null ? (
              <p className="muted">
                {signed(version.total_sup_ha - published.total_sup_ha, formatHa)} ha frente a la
                publicada
              </p>
            ) : null}
          </div>
          <div>
            <dt>Superficie geométrica</dt>
            <dd>{formatHa(sourceUnitsToHa(version.total_geometry_area_source_units))} ha</dd>
            <p className="muted">Calculada del polígono, en metros del CRS declarado</p>
          </div>
          <div>
            <dt>Geometrías inválidas</dt>
            <dd>{formatInt(version.geometry_invalid_count)}</dd>
            <p className="muted">Se guardan tal como vienen, sin reparar</p>
          </div>
        </dl>
      </section>

      <section className="page__section" aria-labelledby="problemas">
        <h3 id="problemas" className="page__section-title">
          Problemas de geometría y de datos
        </h3>
        {review.invalid_geometries.length === 0 ? (
          <p>No hay geometrías inválidas.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">N.º</th>
                  <th scope="col">Predio</th>
                  <th scope="col">Rodal</th>
                  <th scope="col">OBJECTID</th>
                  <th scope="col">Motivo (GEOS)</th>
                </tr>
              </thead>
              <tbody>
                {review.invalid_geometries.map((row) => (
                  <tr key={row.feature_ordinal}>
                    <td>{row.feature_ordinal}</td>
                    <td>{row.nom_predio ?? row.cod_predial ?? 'Sin nombre'}</td>
                    <td>{row.n_rodal ?? 'En blanco'}</td>
                    <td>{row.source_objectid ?? 'Vacío'}</td>
                    <td>{row.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <ul className="flag-list">
          {Object.entries(review.quality_flag_counts)
            .filter(([, count]) => count > 0)
            .map(([flag, count]) => (
              <li key={flag}>
                {qualityFlagLabel(flag)}: <b>{formatInt(count)}</b>
              </li>
            ))}
        </ul>
      </section>

      <section className="page__section" aria-labelledby="cambios">
        <h3 id="cambios" className="page__section-title">
          Cambios respecto de la versión publicada
        </h3>
        {published === null ? (
          <p>
            {version.status === 'published'
              ? 'Esta es la versión publicada.'
              : 'Todavía no hay una versión publicada con la cual comparar.'}
          </p>
        ) : review.comparison_unavailable ? (
          <Notice tone="warn" title="No se pudo calcular la comparación">
            La plataforma no logró comparar las geometrías con la versión N.º{' '}
            {published.shapefile_snapshot_id}. Revise la versión en el mapa antes de publicarla.
          </Notice>
        ) : comparison !== null ? (
          <>
            <p>
              Comparada con la versión N.º {published.shapefile_snapshot_id}. Los polígonos se
              emparejan sólo por su geometría: OBJECTID y el código de rodal no son identificadores
              estables entre exportaciones y se muestran sólo como referencia. Un cambio de forma o
              de atributos no indica por sí solo una intervención en terreno.
            </p>
            <dl className="kpi-row kpi-row--compact">
              <div>
                <dt>Sin cambios</dt>
                <dd>{formatInt(comparison.unchanged_count)}</dd>
              </div>
              {KIND_ORDER.map((kind) => (
                <div key={kind}>
                  <dt>{CHANGE_LABELS[kind]}</dt>
                  <dd>{formatInt(comparison.counts[kind] ?? 0)}</dd>
                </div>
              ))}
            </dl>
            {KIND_ORDER.map((kind) => (
              <ChangeGroup key={kind} kind={kind} items={byKind(kind)} />
            ))}
          </>
        ) : null}
      </section>

      {mayAct ? (
        <section className="page__section decision" aria-labelledby="decision">
          <h3 id="decision" className="page__section-title">
            {action === 'publish' ? 'Publicar esta versión' : 'Restaurar esta versión'}
          </h3>
          <p>
            {action === 'publish'
              ? 'Al publicar, todos los usuarios de Rodales verán esta versión en el mapa.'
              : 'Al restaurar, todos los usuarios de Rodales volverán a ver esta versión en el mapa.'}{' '}
            {published !== null
              ? `La versión N.º ${published.shapefile_snapshot_id} quedará en el historial y podrá restaurarse.`
              : null}
          </p>
          {needsAcknowledgement ? (
            <label className="acknowledge">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
              />
              Revisé las geometrías inválidas y los cambios que requieren revisión, y quiero
              publicar esta versión igualmente.
            </label>
          ) : null}
          {actionError !== null ? (
            <Notice tone="error" title="No se completó la acción">
              <p>{actionError}</p>
              <button type="button" className="button button--ghost" onClick={refresh}>
                Actualizar la revisión
              </button>
            </Notice>
          ) : null}
          <div className="page__actions">
            <button
              type="button"
              className="button"
              disabled={needsAcknowledgement && !acknowledged}
              onClick={() => setConfirming(true)}
            >
              {action === 'publish' ? 'Publicar' : 'Restaurar'}
            </button>
          </div>
        </section>
      ) : null}

      {confirming ? (
        <ConfirmDialog
          title={
            action === 'publish'
              ? `¿Publicar la versión N.º ${version.shapefile_snapshot_id}?`
              : `¿Restaurar la versión N.º ${version.shapefile_snapshot_id}?`
          }
          confirmLabel={action === 'publish' ? 'Publicar' : 'Restaurar'}
          busy={busy}
          onConfirm={() => void activate()}
          onCancel={() => setConfirming(false)}
        >
          <p>
            Todos los usuarios de Rodales verán la versión N.º {version.shapefile_snapshot_id} (
            {formatInt(version.feature_count)} polígonos, {formatHa(version.total_sup_ha)} ha).
          </p>
          {published !== null ? (
            <p>
              La versión N.º {published.shapefile_snapshot_id} dejará de mostrarse y podrá
              restaurarse desde Versiones.
            </p>
          ) : null}
          <p>La acción queda registrada con su nombre y la hora.</p>
        </ConfirmDialog>
      ) : null}
    </PageShell>
  )
}
