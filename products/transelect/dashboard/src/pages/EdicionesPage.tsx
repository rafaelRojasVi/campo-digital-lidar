/**
 * The Datos section's «Ediciones web» pane.
 *
 * Every active edit against the published version, conflicts and orphans
 * first because those need a decision: the planilla wins until someone keeps
 * or discards the web value. The download writes only applied edits into the
 * planilla; the note above the table says how many and why the rest are left
 * out. Results of keep/discard are announced in a polite live region.
 */
import { useCallback, useEffect, useState } from "react";
import {
  EMPTY_FILTERS,
  type ResumenRow,
  type TranselecOverride,
  discardOverride,
  downloadOverridesXlsx,
  keepOverride,
  listOverrides,
  listRows,
  overrideConflictCode,
} from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { RowDetailDrawer } from "../components/RowDetailDrawer";
import {
  AlertBanner,
  LoadingBlock,
  StateBlock,
} from "../components/StateViews";
import { formatInteger } from "../format";
import { classifyFailure, type FailureView } from "../lib/apiState";
import {
  STATUS_LABELS,
  displayValue,
  formatEditDate,
  specFor,
} from "../lib/webEdits";
import { SectionHeader } from "../ui/Primitives";

const ORDER: Record<TranselecOverride["status"], number> = {
  en_conflicto: 0,
  huerfana: 1,
  aplicada: 2,
  incorporada: 3,
};

const CONFLICT_COPY = {
  version_changed:
    "Se publicó otra versión de la planilla mientras tanto. La lista se actualizó; revise y vuelva a intentar.",
  value_changed:
    "La planilla cambió otra vez el valor. La lista se actualizó; revise y vuelva a intentar.",
  not_in_conflict:
    "Esta edición ya no está en conflicto. La lista se actualizó.",
} as const;

function plural(count: number, one: string, many: string): string {
  return `${formatInteger(count)} ${count === 1 ? one : many}`;
}

export function EdicionesPage({
  activeImportId = null,
}: {
  activeImportId?: number | null;
}) {
  const [overrides, setOverrides] = useState<TranselecOverride[] | null>(null);
  const [failure, setFailure] = useState<FailureView | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [confirming, setConfirming] = useState<TranselecOverride | null>(null);
  const [openRow, setOpenRow] = useState<ResumenRow | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void listOverrides().then((result) => {
      if (cancelled) return;
      if (result.ok) {
        setOverrides(result.data);
        setFailure(null);
      } else {
        const view = classifyFailure(result);
        // This pane loads edits; «la importación no se completó» would send
        // the operator to re-import a planilla, which is the wrong action.
        setFailure(
          view.kind === "import_failed" || view.kind === "error"
            ? { ...view, title: "No se pudieron cargar las ediciones web" }
            : view,
        );
      }
    });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  const act = useCallback(
    async (override: TranselecOverride, action: "keep" | "discard") => {
      setBusyId(override.id);
      setActionError(null);
      setStatus("");
      const result =
        action === "keep"
          ? await keepOverride(override.id)
          : await discardOverride(override.id);
      setBusyId(null);
      setConfirming(null);
      if (!result.ok) {
        const code = overrideConflictCode(result.payload);
        setActionError(code ? CONFLICT_COPY[code] : result.error);
        if (code) reload();
        return;
      }
      setStatus(
        action === "keep"
          ? `Se mantuvo el valor web de ${override.field_label} en ${override.pmf}.`
          : `Se descartó la edición de ${override.field_label} en ${override.pmf}.`,
      );
      reload();
    },
    [reload],
  );

  const download = useCallback(async () => {
    setDownloading(true);
    setDownloadError(null);
    const result = await downloadOverridesXlsx();
    setDownloading(false);
    if (!result.ok) {
      setDownloadError(result.error);
      return;
    }
    const url = URL.createObjectURL(result.data.blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = result.data.filename;
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }, []);

  const viewRow = useCallback(async (override: TranselecOverride) => {
    setBusyId(override.id);
    setActionError(null);
    const result = await listRows(
      { ...EMPTY_FILTERS, q: override.pmf },
      { limit: 200 },
    );
    setBusyId(null);
    if (!result.ok) {
      setActionError(result.error);
      return;
    }
    const row = result.data.items.find(
      (entry) => entry.source_row_number === override.source_row_number,
    );
    if (!row) {
      setActionError("No se encontró la fila en la versión publicada.");
      return;
    }
    setOpenRow(row);
  }, []);

  if (failure) {
    return (
      <StateBlock view={failure}>
        <div className="btns">
          <button type="button" className="btn alt" onClick={reload}>
            Reintentar
          </button>
        </div>
      </StateBlock>
    );
  }
  if (!overrides)
    return (
      <LoadingBlock
        label="Cargando las ediciones web…"
        shape="rows"
        lines={4}
      />
    );

  const sorted = [...overrides].sort(
    (a, b) => ORDER[a.status] - ORDER[b.status] || a.id - b.id,
  );
  const count = (s: TranselecOverride["status"]) =>
    overrides.filter((entry) => entry.status === s).length;
  const applied = count("aplicada");
  const notWritten = count("en_conflicto") + count("huerfana");
  const incorporated = count("incorporada");

  return (
    <div className="stack">
      <section aria-labelledby="ediciones-title">
        <SectionHeader
          id="ediciones-title"
          title="Ediciones web"
          meta="Valores cambiados en el panel sobre la versión publicada. La planilla publicada no se modifica."
        />
        <div className="btns no-print edits-download">
          <button
            type="button"
            className="btn"
            disabled={downloading}
            onClick={() => void download()}
            data-testid="download-xlsx"
          >
            {downloading
              ? "Preparando la planilla…"
              : "Descargar planilla con ediciones (.xlsx)"}
          </button>
        </div>
        {downloadError && (
          <AlertBanner title="No se pudo descargar la planilla">
            {downloadError}
          </AlertBanner>
        )}
        <p className="hint" data-testid="download-note">
          La descarga es la planilla publicada con{" "}
          {plural(applied, "celda editada marcada", "celdas editadas marcadas")}{" "}
          «web» (color y nota de Excel).
          {notWritten > 0 &&
            ` ${plural(notWritten, "edición no se escribe", "ediciones no se escriben")} porque la planilla cambió o la fila ya no existe; revíselas abajo.`}
          {incorporated > 0 &&
            ` ${plural(incorporated, "edición ya está", "ediciones ya están")} en la planilla y no necesita marca.`}
        </p>

        {notWritten + incorporated > 0 && (
          <p className="hint" data-testid="conflict-help">
            «En conflicto con la planilla»: la planilla publicada cambió ese
            valor después de la edición y el panel muestra el de la planilla.
            «Mantener valor web» vuelve a mostrar el valor web y lo escribe en
            la descarga; «Descartar» lo borra y queda el de la planilla. «Sin
            fila en la versión publicada»: la edición no se muestra ni se
            descarga. «Ya está en la planilla»: la planilla ya tiene el valor
            web.
          </p>
        )}

        <div
          className="sr-only"
          role="status"
          aria-live="polite"
          data-testid="edits-status"
        >
          {status}
        </div>
        {status && (
          <p className="hint no-print" aria-hidden="true">
            {status}
          </p>
        )}
        {actionError && (
          <AlertBanner title="No se pudo completar la acción">
            {actionError}
          </AlertBanner>
        )}

        {sorted.length === 0 ? (
          <div className="empty" data-testid="overrides-empty">
            Nadie ha editado valores en el panel para la versión publicada.
          </div>
        ) : (
          <div
            className="tablewrap"
            tabIndex={0}
            role="region"
            aria-label="Ediciones web"
          >
            <table
              className="rows-table edits-table"
              data-testid="overrides-table"
            >
              <thead>
                <tr>
                  <th scope="col">Estado</th>
                  <th scope="col">PMF</th>
                  <th scope="col" className="numeric">
                    Fila
                  </th>
                  <th scope="col">Campo</th>
                  <th scope="col">En la planilla</th>
                  <th scope="col">Valor web</th>
                  <th scope="col">Editado por</th>
                  <th scope="col">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((entry) => {
                  const spec = specFor(entry.field);
                  const planilla =
                    entry.status === "en_conflicto"
                      ? entry.planilla_value_now
                      : entry.planilla_value_at_edit;
                  const busy = busyId === entry.id;
                  return (
                    <tr
                      key={entry.id}
                      data-testid={`override-${entry.id}`}
                      data-status={entry.status}
                    >
                      <td>
                        <span
                          className="edit-status"
                          data-status={entry.status}
                        >
                          {STATUS_LABELS[entry.status]}
                        </span>
                      </td>
                      <td id={`override-pmf-${entry.id}`} data-col="pmf">
                        <b>{entry.pmf}</b>
                      </td>
                      <td className="numeric">
                        {entry.source_row_number ?? "—"}
                      </td>
                      <td>{spec.label}</td>
                      <td data-col="planilla">
                        {displayValue(spec, planilla) || "(vacía)"}
                      </td>
                      <td data-col="web">
                        {displayValue(spec, entry.web_value) || "(vacía)"}
                      </td>
                      <td>
                        {entry.created_by_display_name}
                        <br />
                        <span className="hint">
                          {formatEditDate(entry.created_at)}
                        </span>
                      </td>
                      <td>
                        <div className="edit-actions no-print">
                          {entry.status === "en_conflicto" && (
                            <button
                              type="button"
                              className="btn alt small"
                              disabled={busy}
                              aria-describedby={`override-pmf-${entry.id}`}
                              onClick={() => void act(entry, "keep")}
                            >
                              Mantener valor web
                            </button>
                          )}
                          <button
                            type="button"
                            className="btn-link"
                            disabled={busy}
                            aria-describedby={`override-pmf-${entry.id}`}
                            onClick={() => setConfirming(entry)}
                          >
                            Descartar
                          </button>
                          {entry.source_row_number !== null && (
                            <button
                              type="button"
                              className="btn-link"
                              disabled={busy}
                              aria-describedby={`override-pmf-${entry.id}`}
                              onClick={() => void viewRow(entry)}
                            >
                              Ver fila
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {confirming && (
        <ConfirmDialog
          title="Descartar la edición web"
          confirmLabel="Descartar"
          tone="danger"
          busy={busyId === confirming.id}
          onConfirm={() => void act(confirming, "discard")}
          onCancel={() => setConfirming(null)}
        >
          <p>
            Se descartará el valor web de {confirming.field_label} en{" "}
            {confirming.pmf}
            {confirming.status === "aplicada" ||
            confirming.status === "en_conflicto"
              ? "; el panel volverá a mostrar el valor de la planilla."
              : "."}
          </p>
        </ConfirmDialog>
      )}

      {openRow && (
        <RowDetailDrawer
          row={openRow}
          onClose={() => setOpenRow(null)}
          canEdit
          activeImportId={activeImportId}
          onRowEdited={reload}
        />
      )}
    </div>
  );
}
