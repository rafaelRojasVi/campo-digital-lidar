import { useEffect, useId, useMemo, useRef, useState } from 'react'

/**
 * One multi-select filter field (TR-FUNC-018-022).
 *
 * Selected options are OR'd within the field; the API AND's the fields
 * together. The source dashboards use native `<select multiple>` with a
 * "Ctrl + clic" hint, which is unusable on a phone — TR-FUNC-044 requires
 * this to work at 390px — so this is a checkbox popover instead. The filter
 * semantics are unchanged; only the control is.
 */
export function MultiSelectField({
  label,
  options,
  selected,
  onChange,
  placeholderAll = 'Todos',
  triggerRef,
  openSignal = 0,
}: {
  label: string
  options: string[]
  selected: string[]
  onChange: (next: string[]) => void
  placeholderAll?: string
  triggerRef?: React.RefObject<HTMLButtonElement | null>
  /** Increment to programmatically open this field (TR-FUNC-030). */
  openSignal?: number
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const labelId = useId()

  useEffect(() => {
    if (openSignal > 0) setOpen(true)
  }, [openSignal])

  useEffect(() => {
    if (!open) {
      setQuery('')
      return
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  const filteredOptions = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('es-CL')
    if (!needle) return options
    return options.filter((option) => option.toLocaleLowerCase('es-CL').includes(needle))
  }, [options, query])

  const toggle = (option: string) => {
    onChange(
      selected.includes(option)
        ? selected.filter((value) => value !== option)
        : [...selected, option],
    )
  }

  const summary =
    selected.length === 0
      ? placeholderAll
      : selected.length === 1
        ? selected[0]
        : `${selected.length} seleccionados`

  return (
    <div className="field multi-select" ref={containerRef}>
      <span className="field-label" id={labelId}>
        {label}
      </span>
      <button
        type="button"
        ref={triggerRef}
        className={`multi-select-trigger${selected.length > 0 ? ' has-selection' : ''}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-labelledby={labelId}
        disabled={options.length === 0}
        onClick={() => setOpen((value) => !value)}
      >
        <span>{summary}</span>
        <span aria-hidden="true">▾</span>
      </button>

      {open && (
        <div className="multi-select-popover" role="group" aria-labelledby={labelId}>
          {options.length > 8 && (
            <input
              type="search"
              className="multi-select-search"
              placeholder="Buscar…"
              aria-label={`Buscar en ${label}`}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          )}

          <div className="multi-select-options">
            {filteredOptions.map((option) => (
              <label className="multi-select-option" key={option}>
                <input
                  type="checkbox"
                  checked={selected.includes(option)}
                  onChange={() => toggle(option)}
                />
                <span>{option}</span>
              </label>
            ))}
            {filteredOptions.length === 0 && (
              <div className="multi-select-empty">Sin coincidencias</div>
            )}
          </div>

          {selected.length > 0 && (
            <button type="button" className="multi-select-clear" onClick={() => onChange([])}>
              Limpiar selección
            </button>
          )}
        </div>
      )}
    </div>
  )
}
