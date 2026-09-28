import type {
  FeatureCollection,
  ForestrySnapshot,
  SnapshotSummary,
  SourceFeatureDetail,
  SourceFieldComparison,
} from './types.ts'

const API_BASE = '/api/forestry'

/** No Forestry snapshot has been ingested yet (API 404 on latest-ingested). */
export class NoSnapshotError extends Error {
  constructor() {
    super('no forestry snapshot is persisted')
    this.name = 'NoSnapshotError'
  }
}

/** The API responded with an unexpected status (5xx, 404 on known data, …). */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function getJson<T>(path: string): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: 'application/json' },
    })
  } catch {
    throw new ApiError(0, 'network unreachable')
  }

  if (!response.ok) {
    throw new ApiError(response.status, `request failed (${response.status})`)
  }

  return (await response.json()) as T
}

export async function fetchLatestIngestedSnapshot(): Promise<ForestrySnapshot> {
  try {
    return await getJson<ForestrySnapshot>('/snapshots/latest-ingested')
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      throw new NoSnapshotError()
    }
    throw error
  }
}

export function fetchSnapshotSummary(snapshotId: number): Promise<SnapshotSummary> {
  return getJson<SnapshotSummary>(`/snapshots/${snapshotId}`)
}

export function fetchFeatureCollection(snapshotId: number): Promise<FeatureCollection> {
  return getJson<FeatureCollection>(`/snapshots/${snapshotId}/feature-collection`)
}

export function fetchComparison(snapshotId: number): Promise<SourceFieldComparison> {
  return getJson<SourceFieldComparison>(`/snapshots/${snapshotId}/source-field-comparison`)
}

export function fetchFeatureDetail(
  snapshotId: number,
  featureOrdinal: number,
): Promise<SourceFeatureDetail> {
  return getJson<SourceFeatureDetail>(`/snapshots/${snapshotId}/features/${featureOrdinal}`)
}
