import campoDigitalLogo from '../assets/campo-digital-logo.png'
import { formatDate, shortFingerprint } from '../lib/format.ts'
import type { ForestrySnapshot, SnapshotSummary } from '../types.ts'

interface HeaderProps {
  snapshot: ForestrySnapshot
  summary: SnapshotSummary
}

// The brand mark is Campo Digital's own white logo (the same asset the
// Transelec panel bundles, from campodigital.cl), drawn for this dark bar.
// Its alt text carries the company name; the product and estate stay real
// text beside it.
//
// The provenance block deliberately says "última ingesta": the API only
// establishes ingestion order, never that this snapshot is the officially
// current ("vigente") state of the estate.
export function Header({ snapshot, summary }: HeaderProps) {
  return (
    <header className="header">
      <div className="header__brand">
        <img
          className="header__logo"
          src={campoDigitalLogo}
          alt="Campo Digital"
          width={93}
          height={40}
        />
        <div className="header__context">
          <p className="header__product">Gestión Predial Forestal</p>
          <h1 className="header__title">Patrimonio Degenfeld</h1>
        </div>
      </div>

      <dl
        className="header__provenance"
        title="Instantánea más reciente ingerida en la plataforma. No implica que sea la versión oficial vigente del patrimonio."
      >
        <div>
          <dt>Última ingesta</dt>
          <dd>{formatDate(snapshot.created_at)}</dd>
        </div>
        <div>
          <dt>Capa de origen</dt>
          <dd>{snapshot.layer_name}</dd>
        </div>
        <div>
          <dt>CRS almacenado</dt>
          <dd>EPSG:{summary.storage_srid}</dd>
        </div>
        <div>
          <dt>Huella de familia</dt>
          <dd>
            <code>{shortFingerprint(snapshot.family_fingerprint)}</code>
          </dd>
        </div>
      </dl>
    </header>
  )
}
