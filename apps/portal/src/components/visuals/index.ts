import type { ComponentType } from 'react'
import { LidarVisual } from './LidarVisual'
import { ForestalVisual } from './ForestalVisual'
import { TranselecVisual } from './TranselecVisual'
import type { ModuleDefinition } from '../../data/modules'

export const MODULE_VISUALS: Record<ModuleDefinition['accent'], ComponentType> = {
  lidar: LidarVisual,
  forestal: ForestalVisual,
  transelec: TranselecVisual,
}
