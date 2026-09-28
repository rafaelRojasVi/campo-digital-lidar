// es-CL number formatting (thousands ".", decimals ","), matching how the
// stakeholder reads figures such as 10.422,61 ha.

const intFormat = new Intl.NumberFormat('es-CL', { maximumFractionDigits: 0 })

const haFormat = new Intl.NumberFormat('es-CL', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export function formatInt(value: number): string {
  return intFormat.format(value)
}

export function formatHa(value: number): string {
  return haFormat.format(value)
}

/** Geometry area in source units² shown as hectares under the declared metre unit. */
export function sourceUnitsToHa(areaSourceUnits: number): number {
  return areaSourceUnits / 10_000
}

export function formatDate(isoTimestamp: string): string {
  const date = new Date(isoTimestamp)

  if (Number.isNaN(date.getTime())) {
    return isoTimestamp
  }

  return new Intl.DateTimeFormat('es-CL', { dateStyle: 'medium' }).format(date)
}

/** First + last characters of a long fingerprint for compact provenance display. */
export function shortFingerprint(fingerprint: string): string {
  if (fingerprint.length <= 12) {
    return fingerprint
  }

  return `${fingerprint.slice(0, 8)}…${fingerprint.slice(-4)}`
}
