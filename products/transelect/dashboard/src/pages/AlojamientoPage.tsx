/**
 * `/transelec/alojamiento` — where the pilot can live once it stops running
 * on a laptop.
 *
 * Deliberately outside the section navigation (see `AppHeader`'s `NAV`): the
 * five operational sections answer questions about the planilla, and an
 * infrastructure comparison is not one of them. This is a page we send by
 * link to a stakeholder who asked what hosting would cost, not a sixth tab
 * competing with the daily work.
 *
 * The list is ordered by estimated monthly cost, cheapest first: the question
 * the page answers is "what would this cost", and a reader comparing money
 * should not have to sort four cards themselves. Where two alternatives share
 * a band, the composed figure comes before the one that is only an order of
 * magnitude.
 *
 * It renders no data from the API and takes no props. Every figure carries a
 * `basis`: the actual services it adds up, at the list prices published on
 * the providers' own pricing pages and read on REVIEWED (Fly.io machines and
 * Managed Postgres, Supabase Pro, Render web service and Postgres). A reader
 * can therefore check any number by following the link on the same card.
 *
 * **LIMITATION**: a sum of list prices is not a quote. It assumes a sizing
 * (one small app instance, one small managed database, a few GB of files)
 * that nobody has confirmed against real usage, it excludes tax and egress,
 * and provider prices change — hence the review date on the page. The Azure
 * figure alone is not composed here: it stays an order-of-magnitude estimate
 * pending a quote, which is what it says. The repository's own pricing
 * evidence (`docs/platform/environments-and-costs.md`,
 * `docs/research/2026-09-01-platform-runtime-infrastructure-study.md`) is
 * GCP/Azure-oriented and sized for the whole platform, not for this pilot.
 */
import { SectionHeader } from '../ui/Primitives'

/** The review date of the figures below, written once. */
const REVIEWED = '16 de septiembre de 2026'

interface Tool {
  /** What the reader is being sent to, in their own terms. */
  label: string
  /** What this piece does in the alternative — the app, the database, the files. */
  role: string
  href: string
}

interface Option {
  id: string
  name: string
  rank: string
  /** The monthly figure as written, or an explicit "por confirmar". */
  estimate: string
  /** Why that figure is not a quote. Never empty: see the page docstring. */
  estimateNote: string
  intent: string
  /** The services this figure actually adds up, at published list prices. */
  basis: string
  includes: readonly string[]
  /** What we already know about this option from the platform's own record. */
  note?: string
  tools: readonly Tool[]
}

const OPTIONS: readonly Option[] = [
  {
    id: 'render',
    name: 'Render + almacenamiento de archivos',
    rank: 'Opción 1',
    estimate: 'US$20–40 / mes',
    estimateNote: 'Estimación preliminar sobre precios de lista, sujeta a consumo real.',
    basis:
      'Servicio web (US$7) + PostgreSQL administrado de 1 GB (US$19) + disco adicional (US$0,30 por GB).',
    intent:
      'La más económica de las cuatro con servicios administrados: la aplicación y la base de datos en el mismo proveedor, y las planillas en almacenamiento privado.',
    includes: [
      'Aplicación y tablero de Transelec',
      'Base de datos PostgreSQL administrada',
      'Almacenamiento privado de las planillas publicadas',
    ],
    note: 'Es el proveedor donde ya corre hoy el entorno de pruebas del portal, con datos sintéticos.',
    tools: [
      { label: 'Render — planes y precios', role: 'Alojamiento de la aplicación', href: 'https://render.com/pricing' },
      { label: 'Render PostgreSQL', role: 'Base de datos', href: 'https://render.com/docs/postgresql' },
      { label: 'Render Disks', role: 'Almacenamiento de archivos', href: 'https://render.com/docs/disks' },
    ],
  },
  {
    id: 'supabase',
    name: 'Supabase + alojamiento de la aplicación',
    rank: 'Opción 2',
    estimate: 'US$32–40 / mes',
    estimateNote: 'Estimación preliminar sobre precios de lista, sujeta a consumo real.',
    basis:
      'Plan Pro de Supabase (US$25, con 8 GB de base de datos, 100 GB de archivos y respaldos diarios) + el alojamiento de la aplicación en Render o Fly.io (US$7 a US$8).',
    intent:
      'Datos, archivos y respaldos en Supabase; la aplicación se aloja por separado en otro servicio.',
    includes: [
      'Base de datos PostgreSQL administrada',
      'Almacenamiento privado de archivos',
      'Respaldos administrados por el proveedor',
      'Alojamiento de la aplicación contratado aparte',
    ],
    note: 'Supabase no ejecuta por sí solo procesos largos, así que la aplicación necesita igualmente otro servicio. Su región más cercana es São Paulo, no Chile.',
    tools: [
      { label: 'Supabase — planes y precios', role: 'Datos y almacenamiento', href: 'https://supabase.com/pricing' },
      { label: 'Supabase Database', role: 'Base de datos', href: 'https://supabase.com/docs/guides/database/overview' },
      { label: 'Supabase Storage', role: 'Almacenamiento de archivos', href: 'https://supabase.com/docs/guides/storage' },
      { label: 'Fly.io o Render', role: 'Alojamiento de la aplicación', href: 'https://fly.io/pricing/' },
    ],
  },
  {
    id: 'fly',
    name: 'Fly.io',
    rank: 'Opción 3',
    estimate: 'US$45–55 / mes',
    estimateNote: 'Estimación preliminar sobre precios de lista, sujeta a consumo real.',
    basis:
      'Servidor de 1 GB (US$7,78) + Managed Postgres Basic con respaldos y alta disponibilidad (US$38) + 10 GB de disco de base de datos (US$2,80).',
    intent:
      'Aplicación, base de datos y archivos privados en línea con un solo proveedor, a escala pequeña. Es la que proponemos evaluar primero por simplicidad de operación, aunque no sea la más económica.',
    note: 'La cifra incluye la base de datos administrada, que es lo que más pesa. Con una base de datos autoadministrada en el mismo servidor baja a unos US$15 al mes, pero sin respaldos ni alta disponibilidad administrados por el proveedor: no lo recomendamos para datos de Transelec.',
    includes: [
      'Aplicación y tablero de Transelec',
      'Base de datos PostgreSQL administrada',
      'Almacenamiento privado de las planillas publicadas',
      'Respaldos administrados por el proveedor',
    ],
    tools: [
      { label: 'Fly.io — planes y precios', role: 'Alojamiento de la aplicación', href: 'https://fly.io/pricing/' },
      { label: 'Fly Managed Postgres', role: 'Base de datos', href: 'https://fly.io/docs/mpg/' },
      { label: 'Fly Volumes', role: 'Disco persistente', href: 'https://fly.io/docs/volumes/' },
      { label: 'Tigris', role: 'Almacenamiento de archivos', href: 'https://fly.io/docs/tigris/' },
    ],
  },
  {
    id: 'azure',
    name: 'Azure',
    rank: 'Opción 4',
    estimate: 'Desde US$45–55 / mes',
    estimateNote: 'Estimación preliminar de orden de magnitud, sujeta a cotización.',
    basis:
      'No está compuesta servicio por servicio como las anteriores: Azure se cotiza según la configuración elegida, con la calculadora oficial enlazada más abajo.',
    intent:
      'Alternativa integrada con el entorno Microsoft que Transelec ya utiliza, para una etapa posterior del proyecto.',
    includes: [
      'Aplicación y tablero de Transelec',
      'Base de datos PostgreSQL administrada',
      'Almacenamiento privado de archivos',
      'Inicio de sesión con las cuentas corporativas existentes',
    ],
    note: 'Tiene región en Chile (Chile Central) y es la única alternativa que se integra directamente con las cuentas Microsoft de Transelec.',
    tools: [
      { label: 'Calculadora de precios de Azure', role: 'Estimación del costo', href: 'https://azure.microsoft.com/pricing/calculator/' },
      { label: 'Azure Container Apps', role: 'Alojamiento de la aplicación', href: 'https://learn.microsoft.com/azure/container-apps/overview' },
      { label: 'Azure Database for PostgreSQL', role: 'Base de datos', href: 'https://learn.microsoft.com/azure/postgresql/' },
      { label: 'Azure Blob Storage', role: 'Almacenamiento de archivos', href: 'https://azure.microsoft.com/products/storage/blobs' },
      { label: 'Microsoft Entra ID', role: 'Inicio de sesión corporativo', href: 'https://learn.microsoft.com/entra/identity/' },
    ],
  },

]

function ToolLink({ tool, testId }: { tool: Tool; testId: string }) {
  return (
    <li className="host-tool">
      <a
        className="host-tool-link"
        data-testid={testId}
        href={tool.href}
        target="_blank"
        rel="noopener noreferrer"
      >
        {tool.label}
        <span className="sr-only"> (se abre en una pestaña nueva)</span>
      </a>
      <span className="host-tool-role">{tool.role}</span>
    </li>
  )
}

function OptionCard({ option }: { option: Option }) {
  return (
    <article className="host-option" data-testid={`host-${option.id}`}>
      <div className="host-option-head">
        <div>
          <span className="eyebrow">{option.rank}</span>
          <h3>{option.name}</h3>
        </div>
        <div className="host-option-cost">
          <b data-testid={`host-${option.id}-estimate`}>{option.estimate}</b>
          <span data-testid={`host-${option.id}-estimate-note`}>{option.estimateNote}</span>
        </div>
      </div>

      <p className="host-option-intent">{option.intent}</p>

      <p className="host-option-basis" data-testid={`host-${option.id}-basis`}>
        <b>Cómo se calcula:</b> {option.basis}
      </p>

      <div className="host-option-body">
        <div>
          <span className="eyebrow">Qué incluye</span>
          <ul className="host-includes">
            {option.includes.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <span className="eyebrow">Servicios que se contratan</span>
          <ul className="host-tools">
            {option.tools.map((tool, index) => (
              <ToolLink
                key={tool.href + tool.role}
                tool={tool}
                testId={`tool-link-${option.id}-${index}`}
              />
            ))}
          </ul>
        </div>
      </div>

      {option.note && <p className="host-option-note">{option.note}</p>}
    </article>
  )
}

export function AlojamientoPage() {
  return (
    <div className="page enter">
      <SectionHeader
        title="Alojamiento del piloto"
        meta="Dónde puede vivir este tablero cuando deje de estar en un computador y pase a estar en línea."
      />

      <div className="stack">
        <section aria-labelledby="alojamiento-cifras">
          <h2 className="sr-only" id="alojamiento-cifras">
            Cómo leer estas cifras
          </h2>
          <p className="host-disclaimer" data-testid="cost-disclaimer">
            <b>Estas son estimaciones preliminares de infraestructura, no una cotización.</b> Cada
            cifra se calcula sumando los precios de lista publicados por el propio proveedor,
            consultados el {REVIEWED}, para un piloto pequeño: un servidor de aplicación, una base
            de datos administrada y unos pocos GB de archivos. No incluyen impuestos ni tráfico
            fuera de lo previsto, y los precios cambian: el enlace oficial de cada servicio está en
            su tarjeta para poder verificarlos.
          </p>
        </section>

        <section className="ruled" aria-labelledby="alternativas-title">
          <SectionHeader
            id="alternativas-title"
            title="Alternativas de alojamiento"
            meta="Ordenadas de menor a mayor costo mensual estimado, sobre el mismo piloto: un tablero, una base de datos y las planillas publicadas."
          />
          <div className="host-options">
            {OPTIONS.map((option) => (
              <OptionCard key={option.id} option={option} />
            ))}
          </div>
        </section>

        <section className="ruled" aria-labelledby="alcance-title">
          <SectionHeader id="alcance-title" title="Qué incluyen y qué no estas cifras" />
          <div className="host-scope">
            <div>
              <span className="eyebrow">Incluyen</span>
              <ul className="host-includes">
                <li>Servidor de la aplicación</li>
                <li>Base de datos administrada</li>
                <li>Almacenamiento privado de las planillas</li>
                <li>Respaldos del proveedor</li>
              </ul>
            </div>
            <div>
              <span className="eyebrow">No incluyen</span>
              <ul className="host-includes" data-testid="cost-exclusions">
                <li>Dominio propio</li>
                <li>Impuestos</li>
                <li>Licencias de Microsoft 365 / OneDrive</li>
                <li>Horas de desarrollo y soporte</li>
              </ul>
            </div>
          </div>
          <p className="hint" data-testid="next-step">
            Antes de contratar cualquier servicio le presentaré el costo concreto del plan elegido.
          </p>
        </section>
      </div>
    </div>
  )
}
