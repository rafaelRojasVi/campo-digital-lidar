/**
 * The Datos section's access pane — who can use Transelec, and with which role.
 *
 * Administrators only. It lists `GET /auth/admin/product-grants/transelect`
 * and grants a role by email through the POST on the same path. Both routes
 * require MANAGE_ACCESS server-side, so hiding this pane from operators is
 * presentation, not the control.
 *
 * Two deliberate limits:
 *
 *  - A grant only resolves for an address that has already signed in once
 *    (the platform creates the user row at first sign-in). The 404 the API
 *    answers otherwise is translated into that instruction rather than shown
 *    as an error.
 *  - Only `viewer` and `operator` can be granted here. Making someone an
 *    administrator is rare and consequential enough to stay out of a form a
 *    mis-click can submit.
 */
import { type FormEvent, useEffect, useState } from 'react'
import {
  type GrantableRole,
  type ProductGrantee,
  grantTranselecRole,
  listTranselecGrants,
} from '../api'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { classifyFailure, type ApiFailure } from '../lib/apiState'
import { SectionHeader } from '../ui/Primitives'

const ROLE_LABELS: Record<ProductGrantee['role'], string> = {
  admin: 'Administrador',
  operator: 'Operador',
  viewer: 'Lector',
}

const NOT_SIGNED_IN_YET =
  'Esa cuenta todavía no ha iniciado sesión. Pídale que entre una vez con Google (verá "Sin autorización") y vuelva a intentarlo.'

export function AccesosPage() {
  const [grantees, setGrantees] = useState<ProductGrantee[] | null>(null)
  const [failure, setFailure] = useState<ApiFailure | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  const [email, setEmail] = useState('')
  const [role, setRole] = useState<GrantableRole>('viewer')
  const [saving, setSaving] = useState(false)
  const [grantError, setGrantError] = useState<string | null>(null)
  const [granted, setGranted] = useState<ProductGrantee | null>(null)

  useEffect(() => {
    let cancelled = false
    void listTranselecGrants().then((result) => {
      if (cancelled) return
      if (result.ok) {
        setGrantees(result.data)
        setFailure(null)
      } else {
        setGrantees(null)
        setFailure({ status: result.status, error: result.error })
      }
    })
    return () => {
      cancelled = true
    }
  }, [reloadToken])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!email.trim()) return
    setSaving(true)
    setGrantError(null)
    setGranted(null)
    const result = await grantTranselecRole(email, role)
    setSaving(false)
    if (!result.ok) {
      setGrantError(result.status === 404 ? NOT_SIGNED_IN_YET : classifyFailure(result).message)
      return
    }
    setGranted(result.data)
    setEmail('')
    setReloadToken((value) => value + 1)
  }

  if (failure) return <StateBlock view={classifyFailure(failure)} />
  if (!grantees) return <LoadingBlock label="Cargando los accesos…" lines={3} />

  return (
    <div className="stack datos-pane">
      <section>
        <SectionHeader
          title="Accesos a Transelec"
          meta="Sólo cuentas verificadas de campodigital.cl pueden iniciar sesión."
        />

        {granted && (
          <AlertBanner tone="ok" title="Acceso actualizado">
            {granted.email ?? granted.display_name} ahora tiene el rol{' '}
            {ROLE_LABELS[granted.role].toLowerCase()}.
          </AlertBanner>
        )}
        {grantError && <AlertBanner title="No se pudo otorgar el acceso">{grantError}</AlertBanner>}

        <form className="btns" onSubmit={submit} data-testid="grant-form">
          <div className="field">
            <label htmlFor="grant-email">Correo</label>
            <input
              id="grant-email"
              type="text"
              inputMode="email"
              autoComplete="off"
              placeholder="nombre@campodigital.cl"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="grant-role">Rol</label>
            <select
              id="grant-role"
              value={role}
              onChange={(event) => setRole(event.target.value as GrantableRole)}
            >
              <option value="viewer">Lector — consulta el panel</option>
              <option value="operator">Operador — importa y publica planillas</option>
            </select>
          </div>
          <button className="btn" type="submit" disabled={saving || !email.trim()}>
            {saving ? 'Guardando…' : 'Otorgar acceso'}
          </button>
        </form>
      </section>

      <section>
        {grantees.length === 0 ? (
          <div className="empty">Nadie tiene acceso todavía.</div>
        ) : (
          <div className="tablewrap">
            <table className="rows-table" data-testid="grantees">
              <thead>
                <tr>
                  <th scope="col">Nombre</th>
                  <th scope="col">Correo</th>
                  <th scope="col">Rol</th>
                </tr>
              </thead>
              <tbody>
                {grantees.map((grantee) => (
                  <tr key={grantee.app_user_id}>
                    <td>{grantee.display_name}</td>
                    <td>{grantee.email ?? '—'}</td>
                    <td>{ROLE_LABELS[grantee.role]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
