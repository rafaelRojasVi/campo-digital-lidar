import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jsdom implements neither of these; the components use both for the
// scroll-shortcut quick actions. Stubbed so a component test exercises the
// real handler rather than a jsdom-specific branch.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}
if (!window.requestAnimationFrame) {
  window.requestAnimationFrame = ((callback: FrameRequestCallback) =>
    window.setTimeout(() => callback(performance.now()), 0)) as typeof requestAnimationFrame
}

afterEach(() => {
  cleanup()
})
