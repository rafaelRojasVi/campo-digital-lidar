import type { ModuleId } from '../runtime/runtimeConfig'

export interface ModuleDefinition {
  id: ModuleId
  path: string
  title: string
  tagline: string
  description: string
  facts: string[]
  accent: 'lidar' | 'forestal' | 'transelec'
}

/**
 * Stakeholder-facing product facts. Every number here must trace back to
 * source evidence already established elsewhere in the repository — see
 * docs/platform/roadmap.md and each product's own documentation. Do not add
 * a figure here that is not already backed by that evidence.
 */
export const MODULES: ModuleDefinition[] = [
  {
    id: 'lidar',
    path: '/modulo/lidar',
    title: 'Cubicación LiDAR',
    tagline: 'Inspección de nubes de puntos y evidencia de medición',
    description:
      'Procesamiento de nubes de puntos para pilas de madera: localización, geometría de frente y control de calidad, con evidencia trazable de cada corrida.',
    facts: [
      'Inspección forense de LAS/LAZ',
      'Geometría y control de calidad',
      'Vista previa 3D de pilas de madera',
    ],
    accent: 'lidar',
  },
  {
    id: 'forestal',
    path: '/modulo/forestal',
    title: 'Gestión Predial Forestal',
    tagline: 'Polígonos, superficies y visualización cartográfica',
    description:
      'Visualización de predios y rodales sobre mapa satelital, con comparación temporal y simulación local de operaciones de corta.',
    facts: ['1.568 polígonos de origen', '≈10.422,61 ha derivadas de geometría'],
    accent: 'forestal',
  },
  {
    id: 'transelec',
    path: '/modulo/transelec',
    title: 'Transelec',
    tagline: 'Seguimiento de PMF y predios asociados',
    description:
      'Seguimiento de Planes de Manejo Forestal y predios asociados al proyecto Transelec, con trazabilidad hasta la planilla de origen.',
    facts: ['159 PMF', '272 identificadores provisionales de predio', '164,63 ha de superficie de corta'],
    accent: 'transelec',
  },
]

export function findModule(id: string | undefined): ModuleDefinition | undefined {
  return MODULES.find((module) => module.id === id)
}
