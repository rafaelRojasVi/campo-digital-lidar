import type { ProductKey } from '../lib/platformApi'

export interface ProductCard {
  key: ProductKey
  title: string
  description: string
  /** Where the product lives on this origin; null while it is not online. */
  href: string | null
}

export const PRODUCT_CARDS: readonly ProductCard[] = [
  {
    key: 'transelect',
    title: 'Transelec',
    description: 'Seguimiento de planes de manejo forestal y predios asociados.',
    href: '/transelec/',
  },
  {
    key: 'forestry',
    title: 'Rodales',
    description: 'Patrimonio Degenfeld: rodales, usos de suelo y superficies.',
    href: null,
  },
  {
    key: 'lidar',
    title: 'Cubicación LiDAR',
    description: 'Inspección de nubes de puntos de pilas de madera.',
    href: null,
  },
]

export const GOOGLE_LOGIN_PATH = '/api/auth/google/login'
