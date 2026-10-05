/**
 * A confirmation opened over the row drawer.
 *
 * The drawer listens for Escape and Tab on the document, so a dialog on top
 * of it keeps both to itself: Escape cancels only the dialog, and Tab cycles
 * only its buttons. Rendered into document.body, like the drawer.
 */
import type { ComponentProps, KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { ConfirmDialog } from './ConfirmDialog'

const FOCUSABLE = 'button:not([disabled])'

export function DrawerConfirm(props: ComponentProps<typeof ConfirmDialog>) {
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      event.preventDefault()
      props.onCancel()
    } else if (event.key === 'Tab') {
      const buttons = [...event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE)]
      if (buttons.length === 0) return
      event.stopPropagation()
      const first = buttons[0]
      const last = buttons[buttons.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
  }
  return createPortal(
    <div onKeyDown={onKeyDown}>
      <ConfirmDialog {...props} />
    </div>,
    document.body,
  )
}
