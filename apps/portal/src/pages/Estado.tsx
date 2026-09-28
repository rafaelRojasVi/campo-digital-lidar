import { MODULES } from '../data/modules'
import { Link } from '../router/Router'
import { moduleStatusFor } from '../runtime/runtimeConfig'
import { useRuntimeConfig } from '../runtime/useRuntimeConfig'

export function Estado() {
  const { config, loading } = useRuntimeConfig()
  const isStaging = config.environment === 'staging'

  return (
    <div className="estado">
      <p>
        <Link to="/">← Campo Digital</Link>
      </p>
      <h1>{isStaging ? 'Estado del entorno de staging' : 'Estado del entorno local'}</h1>
      <p className="estado__note">
        {isStaging
          ? 'Entorno de staging público. No contiene datos reales de clientes.'
          : 'Vista de diagnóstico para desarrollo. No representa disponibilidad en producción.'}
      </p>

      {loading ? (
        <p>Cargando…</p>
      ) : (
        <table className="estado__table">
          <thead>
            <tr>
              <th>Módulo</th>
              <th>Estado</th>
              <th>URL{isStaging ? '' : ' local'}</th>
              {!isStaging && <th>Iniciado por Campo Demo</th>}
              <th>Mediciones persistidas</th>
            </tr>
          </thead>
          <tbody>
            {MODULES.map((module) => {
              const status = moduleStatusFor(config, module.id)
              return (
                <tr key={module.id}>
                  <td>{module.title}</td>
                  <td>{status.status}</td>
                  <td>
                    <code>{status.url ?? '—'}</code>
                  </td>
                  {!isStaging && (
                    <td>
                      {status.owned === undefined ? '—' : status.owned ? 'sí' : 'no (ya estaba activo)'}
                    </td>
                  )}
                  <td>{status.measurementCount === undefined ? '—' : status.measurementCount}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      <p className="estado__generated">
        Generado: <code>{config.generatedAt ?? '—'}</code>
      </p>
    </div>
  )
}
