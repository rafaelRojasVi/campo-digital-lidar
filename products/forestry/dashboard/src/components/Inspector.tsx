import { useEffect, useState } from 'react'
import { fetchFeatureDetail } from '../api.ts'
import { formatHa } from '../lib/format.ts'
import { qualityFlagLabel } from '../lib/qualityLabels.ts'
import { sourceUnitsToHa } from '../lib/format.ts'
import type { GeoFeature, SourceFeatureDetail } from '../types.ts'

interface InspectorProps {
  snapshotId: number
  feature: GeoFeature
  onClose: () => void
  onZoom: () => void
}

type DetailState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; detail: SourceFeatureDetail }

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="inspector__row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

// Detail view of one selected source polygon: listing fields immediately from
// the loaded collection, full attribute row + validity evidence from the
// per-feature endpoint.
export function Inspector({ snapshotId, feature, onClose, onZoom }: InspectorProps) {
  const [detailState, setDetailState] = useState<DetailState>({ status: 'loading' })
  const [attributesOpen, setAttributesOpen] = useState(false)

  const p = feature.properties

  useEffect(() => {
    let cancelled = false

    fetchFeatureDetail(snapshotId, p.feature_ordinal)
      .then((detail) => {
        if (!cancelled) {
          setDetailState({ status: 'ready', detail })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDetailState({ status: 'error' })
        }
      })

    return () => {
      cancelled = true
    }
  }, [snapshotId, p.feature_ordinal])

  const usoDiffers = p.uso_2024 !== p.uso_2026
  const codeDiffers = p.cod_uso !== p.cod_uso_2026
  const detail = detailState.status === 'ready' ? detailState.detail : null

  return (
    <aside className="inspector" aria-label="Detalle del polígono seleccionado">
      <div className="inspector__head">
        <div>
          <h2 className="inspector__title">
            {p.nom_predio ?? 'Predio sin nombre'}
            {p.cod_predial !== null ? (
              <span className="inspector__code"> {p.cod_predial}</span>
            ) : null}
          </h2>
          <p className="inspector__subtitle">
            {p.n_rodal !== null && p.n_rodal !== ''
              ? `Rodal ${p.n_rodal}`
              : 'Sin rodal en la fuente'}
          </p>
        </div>
        <div className="inspector__head-actions">
          <button type="button" className="button button--ghost" onClick={onZoom}>
            Acercar
          </button>
          <button
            type="button"
            className="inspector__close"
            onClick={onClose}
            aria-label="Cerrar detalle"
          >
            ×
          </button>
        </div>
      </div>

      <div className="inspector__body">
        <section className="inspector__section">
          <h3>Uso del suelo</h3>
          <dl>
            <Row label="Uso 2026" value={p.uso_2026 ?? '(vacío)'} />
            <Row label="Uso 2024" value={p.uso_2024 ?? '(vacío)'} />
            {usoDiffers ? (
              <p className="inspector__difference">Los campos Uso2024 y Uso2026 difieren.</p>
            ) : null}
            <Row label="Código 2026 (CodUso_2026)" value={p.cod_uso_2026 ?? '(vacío)'} />
            <Row label="Código estado 2024 (Cod_Uso)" value={p.cod_uso ?? '(vacío)'} />
            {codeDiffers ? (
              <p className="inspector__difference">
                Los campos Cod_Uso y CodUso_2026 difieren.
              </p>
            ) : null}
            <Row label="Descripción (DescUso)" value={p.desc_uso ?? '(vacío)'} />
          </dl>
        </section>

        <section className="inspector__section">
          <h3>Superficie</h3>
          <dl>
            <Row
              label="Sup_ha (fuente)"
              value={p.sup_ha !== null ? `${formatHa(p.sup_ha)} ha` : '(vacío)'}
            />
            <Row
              label="Área derivada de la geometría"
              value={`${formatHa(sourceUnitsToHa(p.geometry_area_source_units))} ha`}
            />
          </dl>
        </section>

        <section className="inspector__section">
          <h3>Geometría</h3>
          <dl>
            <Row label="Validez OGC" value={p.geometry_is_valid ? 'Válida' : 'Inválida'} />
            {detail !== null && detail.geometry_invalid_reason !== null ? (
              <Row label="Motivo" value={detail.geometry_invalid_reason} />
            ) : null}
          </dl>
        </section>

        {p.quality_flags.length > 0 ? (
          <section className="inspector__section">
            <h3>Evidencia de calidad de datos</h3>
            <ul className="inspector__flags">
              {p.quality_flags.map((flag) => (
                <li key={flag}>{qualityFlagLabel(flag)}</li>
              ))}
            </ul>
          </section>
        ) : null}

        <section className="inspector__section">
          <h3>Evidencia de fuente</h3>
          <dl>
            <Row
              label="OBJECTID (evidencia de fuente)"
              value={p.source_objectid !== null ? String(p.source_objectid) : '(vacío)'}
            />
            <Row label="Registro N° en el shapefile" value={String(p.feature_ordinal)} />
            <Row label="Instantánea" value={String(snapshotId)} />
          </dl>
        </section>

        <section className="inspector__section">
          {detailState.status === 'loading' ? (
            <p className="inspector__loading">Cargando atributos originales…</p>
          ) : null}
          {detailState.status === 'error' ? (
            <p className="inspector__error">
              No fue posible cargar el detalle completo desde la API.
            </p>
          ) : null}
          {detail !== null ? (
            <>
              <button
                type="button"
                className="inspector__attributes-toggle"
                aria-expanded={attributesOpen}
                onClick={() => setAttributesOpen((open) => !open)}
              >
                {attributesOpen ? 'Ocultar atributos originales' : 'Atributos originales'} (
                {Object.keys(detail.source_attributes).length} campos)
              </button>
              {attributesOpen ? (
                <dl className="inspector__attributes">
                  {Object.entries(detail.source_attributes).map(([key, value]) => (
                    <Row
                      key={key}
                      label={key}
                      value={value === null || value === '' ? '(vacío)' : String(value)}
                    />
                  ))}
                </dl>
              ) : null}
            </>
          ) : null}
        </section>
      </div>
    </aside>
  )
}
