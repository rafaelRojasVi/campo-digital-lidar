import { useEffect, useMemo, useState } from 'react'
import './App.css'
import {
  artifactUrl,
  getRun,
  listComparisons,
  listRuns,
  type MeasurementRun,
  type VolumeComparisonRecord,
} from './api'

function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) {
    return '—'
  }

  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
  })
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—'
  }

  return `${(value * 100).toFixed(1)}%`
}

function formatDate(value: string | null): string {
  if (!value) {
    return '—'
  }

  return new Date(value).toLocaleString()
}

function App() {
  const [runs, setRuns] = useState<MeasurementRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [run, setRun] = useState<MeasurementRun | null>(null)
  const [comparisons, setComparisons] = useState<VolumeComparisonRecord[]>([])
  const [loadingRuns, setLoadingRuns] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const data = await listRuns()

        if (cancelled) {
          return
        }

        setRuns(data)
        setSelectedRunId(data[0]?.run_id ?? null)
      } catch (reason) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : String(reason))
        }
      } finally {
        if (!cancelled) {
          setLoadingRuns(false)
        }
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!selectedRunId) {
      return
    }

    let cancelled = false

    async function loadDetail() {
      setLoadingDetail(true)
      setError(null)

      try {
        const [runData, comparisonData] = await Promise.all([
          getRun(selectedRunId as string),
          listComparisons(selectedRunId as string),
        ])

        if (cancelled) {
          return
        }

        setRun(runData)
        setComparisons(comparisonData)
      } catch (reason) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : String(reason))
        }
      } finally {
        if (!cancelled) {
          setLoadingDetail(false)
        }
      }
    }

    void loadDetail()

    return () => {
      cancelled = true
    }
  }, [selectedRunId])

  const blockers = useMemo(
    () => run?.warnings.filter((warning) => warning.severity === 'blocker') ?? [],
    [run],
  )

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <p className="eyebrow">Campo Digital</p>
          <h1>LiDAR Measurement Console</h1>
          <p className="brand-copy">
            Read-only engineering view of persisted timber-stack measurements.
          </p>
        </div>

        <div className="runs-heading">
          <span>Measurement runs</span>
          <span className="count">{runs.length}</span>
        </div>

        <div className="run-list">
          {loadingRuns && <p className="muted">Loading runs…</p>}

          {!loadingRuns && runs.length === 0 && (
            <p className="muted">No persisted runs found.</p>
          )}

          {runs.map((item) => (
            <button
              className={`run-item ${
                selectedRunId === item.run_id ? 'selected' : ''
              }`}
              key={item.run_id}
              onClick={() => setSelectedRunId(item.run_id)}
              type="button"
            >
              <span className={`status-dot status-${item.status}`} />
              <span className="run-item-content">
                <strong>{item.run_id}</strong>
                <small>{formatDate(item.completed_at ?? item.started_at)}</small>
              </span>
            </button>
          ))}
        </div>
      </aside>

      <main className="content">
        {error && (
          <section className="error-banner">
            <strong>API error</strong>
            <span>{error}</span>
          </section>
        )}

        {!selectedRunId && !loadingRuns && (
          <section className="empty-state">
            <h2>No measurement selected</h2>
            <p>Create a persisted measurement run before opening the console.</p>
          </section>
        )}

        {loadingDetail && (
          <section className="empty-state">
            <p>Loading measurement…</p>
          </section>
        )}

        {run && !loadingDetail && (
          <>
            <header className="page-header">
              <div>
                <p className="eyebrow">Measurement run</p>
                <h2>{run.run_id}</h2>
                <p className="subtitle">
                  Completed {formatDate(run.completed_at)}
                </p>
              </div>

              <span className={`status-badge status-${run.status}`}>
                {run.status}
              </span>
            </header>

            {blockers.length > 0 && (
              <section className="blocker-panel">
                <div className="section-heading">
                  <h3>Measurement blockers</h3>
                  <span>{blockers.length}</span>
                </div>

                {blockers.map((warning) => (
                  <div className="blocker" key={warning.code}>
                    <strong>{warning.code}</strong>
                    <p>{warning.message}</p>
                  </div>
                ))}
              </section>
            )}

            <section className="metric-grid">
              <article className="metric-card">
                <span>Selected points</span>
                <strong>
                  {formatNumber(run.timber_stack?.point_count_selected, 0)}
                </strong>
                <small>
                  {formatPercent(run.timber_stack?.selected_fraction)} of input
                </small>
              </article>

              <article className="metric-card">
                <span>Front span</span>
                <strong>
                  {formatNumber(run.front_cross_section?.longitudinal_span)}
                </strong>
                <small>source units</small>
              </article>

              <article className="metric-card">
                <span>Median height</span>
                <strong>
                  {formatNumber(run.front_cross_section?.median_height)}
                </strong>
                <small>source units</small>
              </article>

              <article className="metric-card">
                <span>Front area</span>
                <strong>
                  {formatNumber(run.front_cross_section?.rectangle_area)}
                </strong>
                <small>source-units² · rectangle</small>
              </article>

              <article className="metric-card">
                <span>Volume results</span>
                <strong>{run.results.length}</strong>
                <small>raw geometric estimates</small>
              </article>

              <article className="metric-card">
                <span>Comparisons</span>
                <strong>{comparisons.length}</strong>
                <small>reference validations</small>
              </article>
            </section>

            <div className="two-column">
              <section className="panel">
                <div className="section-heading">
                  <h3>Geometry</h3>
                </div>

                <dl className="detail-list">
                  <div>
                    <dt>Input points</dt>
                    <dd>
                      {formatNumber(run.timber_stack?.point_count_input, 0)}
                    </dd>
                  </div>
                  <div>
                    <dt>Selected points</dt>
                    <dd>
                      {formatNumber(run.timber_stack?.point_count_selected, 0)}
                    </dd>
                  </div>
                  <div>
                    <dt>Components</dt>
                    <dd>{formatNumber(run.timber_stack?.detected_components, 0)}</dd>
                  </div>
                  <div>
                    <dt>Longitudinal coverage</dt>
                    <dd>
                      {formatPercent(run.timber_stack?.longitudinal_coverage)}
                    </dd>
                  </div>
                  <div>
                    <dt>Maximum front height</dt>
                    <dd>
                      {formatNumber(run.front_cross_section?.maximum_height)}
                    </dd>
                  </div>
                  <div>
                    <dt>Trapezoid front area</dt>
                    <dd>
                      {formatNumber(run.front_cross_section?.trapezoid_area)}
                    </dd>
                  </div>
                </dl>
              </section>

              <section className="panel">
                <div className="section-heading">
                  <h3>Provenance</h3>
                </div>

                <dl className="detail-list">
                  <div>
                    <dt>Schema</dt>
                    <dd>{run.schema_version}</dd>
                  </div>
                  <div>
                    <dt>Code version</dt>
                    <dd>{run.code_version ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Source checksum</dt>
                    <dd className="mono">
                      {run.source_sha256
                        ? `${run.source_sha256.slice(0, 16)}…`
                        : '—'}
                    </dd>
                  </div>
                  <div>
                    <dt>Warnings</dt>
                    <dd>{run.warnings.length}</dd>
                  </div>
                  <div>
                    <dt>Artifacts</dt>
                    <dd>{run.artifacts.length}</dd>
                  </div>
                </dl>
              </section>
            </div>

            <section className="panel">
              <div className="section-heading">
                <h3>Geometric volume results</h3>
                <span>{run.results.length}</span>
              </div>

              {run.results.length === 0 ? (
                <p className="muted">
                  No volume result is persisted for this run.
                </p>
              ) : (
                <div className="result-grid">
                  {run.results.map((result, index) => (
                    <article className="result-card" key={`${result.method}-${index}`}>
                      <p className="eyebrow">Result {index + 1}</p>
                      <h4>{result.method}</h4>
                      <div className="volume-value">
                        {formatNumber(result.volume, 6)}
                      </div>
                      <p>{result.volume_unit}</p>

                      {result.parameters.commercial_cubicacion === false && (
                        <span className="method-label">
                          Geometric only · not commercial cubicación
                        </span>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </section>

              <section className="panel">
                <div className="section-heading">
                  <h3>Reference comparisons</h3>
                  <span>{comparisons.length}</span>
                </div>

                {comparisons.length === 0 ? (
                  <p className="muted">
                    No compatible reference comparison has been persisted.
                  </p>
                ) : (
                  <div className="comparison-table">
                    {comparisons.map((record) => (
                      <div
                        className="comparison-row"
                        key={record.comparison_id}
                      >
                        <div>
                          <strong>{record.comparison_id}</strong>
                          <small>{record.comparison.reference.method}</small>
                        </div>
                        <div>
                          <span>Estimate</span>
                          <strong>
                            {formatNumber(
                              record.comparison.estimate_value,
                              6,
                            )}
                          </strong>
                        </div>
                        <div>
                          <span>Reference</span>
                          <strong>
                            {formatNumber(
                              record.comparison.reference.value,
                              6,
                            )}
                          </strong>
                        </div>
                        <div>
                          <span>Signed error</span>
                          <strong>
                            {formatNumber(
                              record.comparison.signed_error,
                              6,
                            )}
                          </strong>
                        </div>
                        <div>
                          <span>Absolute % error</span>
                          <strong>
                            {record.comparison.absolute_percent_error === null
                              ? '—'
                              : `${record.comparison.absolute_percent_error.toFixed(2)}%`}
                          </strong>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>

            <section className="panel">
              <div className="section-heading">
                <h3>Artifacts</h3>
                <span>{run.artifacts.length}</span>
              </div>

              {run.artifacts.length === 0 ? (
                <p className="muted">No registered artifacts.</p>
              ) : (
                <div className="artifact-grid">
                  {run.artifacts.map((artifact) => {
                    const url = artifactUrl(run.run_id, artifact.path)
                    const isImage = artifact.media_type?.startsWith('image/')

                    return (
                      <article className="artifact-card" key={artifact.path}>
                        {isImage && (
                          <a href={url} target="_blank" rel="noreferrer">
                            <img
                              src={url}
                              alt={artifact.description ?? artifact.kind}
                            />
                          </a>
                        )}

                        <div className="artifact-copy">
                          <p className="eyebrow">{artifact.kind}</p>
                          <strong>{artifact.path}</strong>
                          <p>{artifact.description}</p>
                          <a href={url} target="_blank" rel="noreferrer">
                            Open artifact
                          </a>
                        </div>
                      </article>
                    )
                  })}
                </div>
              )}
            </section>

            <section className="panel warning-list">
              <div className="section-heading">
                <h3>Diagnostics</h3>
                <span>{run.warnings.length}</span>
              </div>

              {run.warnings.map((warning) => (
                <article
                  className={`diagnostic diagnostic-${warning.severity}`}
                  key={`${warning.code}-${warning.message}`}
                >
                  <div>
                    <strong>{warning.code}</strong>
                    <span>{warning.severity}</span>
                  </div>
                  <p>{warning.message}</p>
                </article>
              ))}
            </section>
          </>
        )}
      </main>
    </div>
  )
}

export default App
