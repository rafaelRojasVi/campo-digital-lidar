export type WarningSeverity = 'info' | 'warning' | 'blocker'

export interface MeasurementWarning {
  code: string
  severity: WarningSeverity
  message: string
}

export interface MeasurementArtifact {
  kind: string
  path: string
  media_type: string | null
  description: string | null
}

export interface TimberStackSummary {
  point_count_input: number
  point_count_selected: number
  selected_fraction: number
  detected_components: number | null
  longitudinal_coverage: number | null
  vertical_extent_fraction: number | null
  transverse_extent_fraction: number | null
  parameters: Record<string, unknown>
}

export interface FrontCrossSectionSummary {
  longitudinal_span: number
  median_height: number
  maximum_height: number
  rectangle_area: number
  trapezoid_area: number
  valid_bin_fraction: number
  parameters: Record<string, unknown>
}

export interface VolumeResult {
  method: string
  volume: number
  volume_unit: 'm3' | 'cubic_units_unspecified'
  point_count_input: number
  point_count_used: number
  parameters: Record<string, unknown>
  warnings: string[]
  runtime_seconds: number
  provenance: Record<string, unknown>
}

export interface MeasurementRun {
  schema_version: string
  run_id: string
  source_path: string
  source_sha256: string | null
  status: 'started' | 'completed' | 'failed'
  started_at: string
  completed_at: string | null
  code_version: string | null
  coordinate_metadata: Record<string, unknown> | null
  timber_stack: TimberStackSummary | null
  front_cross_section: FrontCrossSectionSummary | null
  log_detection: Record<string, unknown> | null
  results: VolumeResult[]
  reference: Record<string, unknown> | null
  warnings: MeasurementWarning[]
  artifacts: MeasurementArtifact[]
  provenance: Record<string, unknown>
  notes: string | null
}

export interface ReferenceMeasurement {
  label: string
  value: number
  unit: 'm3' | 'cubic_units_unspecified'
  method: string
  recorded_at: string | null
  notes: string | null
}

export interface VolumeComparison {
  estimate_method: string
  estimate_value: number
  reference: ReferenceMeasurement
  unit: 'm3' | 'cubic_units_unspecified'
  signed_error: number
  absolute_error: number
  relative_error: number | null
  absolute_relative_error: number | null
  percent_error: number | null
  absolute_percent_error: number | null
}

export interface VolumeComparisonRecord {
  schema_version: string
  comparison_id: string
  run_id: string
  estimate_result_index: number
  comparison: VolumeComparison
  created_at: string
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`)

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`

    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) {
        detail = payload.detail
      }
    } catch {
      // Preserve the HTTP fallback.
    }

    throw new Error(detail)
  }

  return response.json() as Promise<T>
}

export function listRuns(): Promise<MeasurementRun[]> {
  return getJson<MeasurementRun[]>('/runs')
}

export function getRun(runId: string): Promise<MeasurementRun> {
  return getJson<MeasurementRun>(`/runs/${encodeURIComponent(runId)}`)
}

export function listComparisons(
  runId: string,
): Promise<VolumeComparisonRecord[]> {
  return getJson<VolumeComparisonRecord[]>(
    `/runs/${encodeURIComponent(runId)}/comparisons`,
  )
}

export function artifactUrl(
  runId: string,
  artifactPath: string,
): string {
  return `/api/runs/${encodeURIComponent(runId)}/artifacts/${artifactPath
    .split('/')
    .map(encodeURIComponent)
    .join('/')}`
}
