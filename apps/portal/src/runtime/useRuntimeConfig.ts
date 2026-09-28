import { useEffect, useState } from 'react'
import { getCampoEnvironment } from './environment'
import type { CampoRuntimeConfig } from './runtimeConfig'
import { buildStagingRuntimeConfig, fetchRuntimeConfig } from './runtimeConfig'

export interface RuntimeConfigState {
  config: CampoRuntimeConfig
  loading: boolean
}

/**
 * STAGING has no dynamic file to fetch, so its config is knowable
 * synchronously, before the first render — computed directly in the
 * useState initializer rather than via an effect, so no cascading render
 * is needed for a value we already have.
 */
function initialState(): RuntimeConfigState {
  if (getCampoEnvironment() === 'staging') {
    return { config: buildStagingRuntimeConfig(), loading: false }
  }
  return { config: { environment: 'local', modules: {} }, loading: true }
}

export function useRuntimeConfig(): RuntimeConfigState {
  const [state, setState] = useState<RuntimeConfigState>(initialState)

  useEffect(() => {
    if (getCampoEnvironment() === 'staging') {
      return
    }

    const controller = new AbortController()

    fetchRuntimeConfig(controller.signal).then((config) => {
      if (!controller.signal.aborted) {
        setState({ config, loading: false })
      }
    })

    return () => controller.abort()
  }, [])

  return state
}
