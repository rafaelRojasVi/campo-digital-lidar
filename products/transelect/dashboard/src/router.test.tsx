import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RouterProvider, useRouter } from './router'

describe('RouterProvider', () => {
  it('treats /transelec/ (the served base) like /transelec', () => {
    let seen = ''
    function Probe() {
      seen = useRouter().pathname
      return null
    }
    render(
      <RouterProvider initialPath="/transelec/">
        <Probe />
      </RouterProvider>,
    )
    expect(seen).toBe('/transelec')
  })

  it('keeps the root path as is', () => {
    let seen = ''
    function Probe() {
      seen = useRouter().pathname
      return null
    }
    render(
      <RouterProvider initialPath="/">
        <Probe />
      </RouterProvider>,
    )
    expect(seen).toBe('/')
  })
})
