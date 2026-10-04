import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TranselecOverride } from "../api";
import { RouterProvider } from "../router";
import { EdicionesPage } from "./EdicionesPage";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    listRows: vi.fn(),
    listOverrides: vi.fn(),
    keepOverride: vi.fn(),
    discardOverride: vi.fn(),
    downloadOverridesXlsx: vi.fn(),
  };
});

vi.mock("../components/RowDetailDrawer", () => ({
  RowDetailDrawer: ({
    row,
    sourceFields,
  }: {
    row: { source_row_number: number };
    sourceFields?: readonly string[] | null;
  }) => (
    <div data-testid="drawer" data-source-fields={sourceFields?.join(",")}>
      fila {row.source_row_number}
    </div>
  ),
}));

const {
  listOverrides,
  keepOverride,
  discardOverride,
  listRows,
  downloadOverridesXlsx,
} = await import("../api");

const make = (
  id: number,
  status: TranselecOverride["status"],
): TranselecOverride => ({
  id,
  field: "estado_resumido",
  field_label: "Estado resumido",
  status,
  pmf: `MP00${id}`,
  rol: "1",
  numero_predio: "1",
  numero_area_corta: "A1",
  source_row_number: status === "huerfana" ? null : id + 1,
  web_value: "Aprobado",
  planilla_value_at_edit: "En tramite",
  planilla_value_now: status === "en_conflicto" ? "Desistido" : "En tramite",
  created_by_display_name: "Ana Pérez",
  created_at: "2026-10-04T15:00:00+00:00",
});

describe("EdicionesPage", () => {
  beforeEach(() => {
    vi.mocked(listOverrides).mockReset();
    vi.mocked(keepOverride).mockReset();
    vi.mocked(listRows).mockReset();
    vi.mocked(discardOverride).mockReset();
    vi.mocked(downloadOverridesXlsx).mockReset();
  });

  it("lists edits, says what the download writes, and keeps a conflict", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [make(1, "en_conflicto"), make(2, "huerfana"), make(3, "aplicada")],
    });
    vi.mocked(keepOverride).mockResolvedValue({
      ok: true,
      data: { override_id: 9 },
    });
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    );

    expect(await screen.findByTestId("download-xlsx")).toHaveRole("button");
    expect(screen.getByTestId("download-note")).toHaveTextContent(
      "1 celda editada marcada",
    );
    expect(screen.getByTestId("download-note")).toHaveTextContent(
      "2 ediciones no se escriben",
    );
    const conflict = screen.getByTestId("override-1");
    expect(conflict).toHaveTextContent("Desistido");
    await userEvent.click(
      within(conflict).getByRole("button", { name: "Mantener valor web" }),
    );
    expect(keepOverride).toHaveBeenCalledWith(1);
  });

  it("says so when nobody edited anything", async () => {
    vi.mocked(listOverrides).mockResolvedValue({ ok: true, data: [] });
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    );
    expect(await screen.findByTestId("overrides-empty")).toBeInTheDocument();
  });

  it("puts conflicts and orphans first, and announces what keeping did", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [make(1, "aplicada"), make(2, "huerfana"), make(3, "en_conflicto")],
    });
    vi.mocked(keepOverride).mockResolvedValue({
      ok: true,
      data: { override_id: 9 },
    });
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    );
    const table = await screen.findByTestId("overrides-table");
    const ids = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => row.getAttribute("data-testid"));
    expect(ids).toEqual(["override-3", "override-2", "override-1"]);
    expect(
      within(screen.getByTestId("override-3")).getByText(
        "En conflicto con la planilla",
      ),
    ).toBeInTheDocument();
    await userEvent.click(
      within(screen.getByTestId("override-3")).getByRole("button", {
        name: "Mantener valor web",
      }),
    );
    expect(screen.getByTestId("edits-status")).toHaveTextContent(
      "Se mantuvo el valor web",
    );
  });

  it("asks before discarding and shows a Spanish message for a 409", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [make(1, "en_conflicto")],
    });
    vi.mocked(keepOverride).mockResolvedValue({
      ok: false,
      status: 409,
      error: "x",
      payload: { code: "value_changed" },
    });
    vi.mocked(discardOverride).mockResolvedValue({ ok: true, data: undefined });
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    );
    const row = await screen.findByTestId("override-1");
    await userEvent.click(
      within(row).getByRole("button", { name: "Mantener valor web" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La planilla cambió otra vez el valor",
    );

    await userEvent.click(
      within(row).getByRole("button", { name: "Descartar" }),
    );
    expect(discardOverride).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("confirm-accept"));
    expect(discardOverride).toHaveBeenCalledWith(1);
  });

  it("shows an error state with a retry when the list cannot be read", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: false,
      status: 500,
      error: "boom",
    });
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    );
    expect(
      await screen.findByRole("button", { name: "Reintentar" }),
    ).toBeInTheDocument();
  });

  it("offers actions only where they apply", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [make(1, "aplicada"), make(2, "huerfana"), make(3, "en_conflicto")],
    });
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    );
    const applied = await screen.findByTestId("override-1");
    const orphan = screen.getByTestId("override-2");
    const conflict = screen.getByTestId("override-3");
    const keep = { name: "Mantener valor web" };
    expect(within(applied).queryByRole("button", keep)).toBeNull();
    expect(within(orphan).queryByRole("button", keep)).toBeNull();
    expect(within(conflict).getByRole("button", keep)).toBeInTheDocument();
    expect(
      within(orphan).queryByRole("button", { name: "Ver fila" }),
    ).toBeNull();
    expect(
      within(applied).getByRole("button", { name: "Ver fila" }),
    ).toBeInTheDocument();
    expect(
      within(orphan).getByRole("button", { name: "Descartar" }),
    ).toBeInTheDocument();
  });

  it("opens the matching row from Ver fila", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [make(1, "aplicada")],
    });
    vi.mocked(listRows).mockResolvedValue({
      ok: true,
      data: {
        items: [{ source_row_number: 99 }, { source_row_number: 2 }] as never,
        next_cursor: null,
        has_more: false,
        total_count: 2,
      },
    });
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    );
    const row = await screen.findByTestId("override-1");
    await userEvent.click(
      within(row).getByRole("button", { name: "Ver fila" }),
    );
    expect(await screen.findByTestId("drawer")).toHaveTextContent("fila 2");
    expect(vi.mocked(listRows).mock.calls[0][0]).toMatchObject({ q: "MP001" });
  });

  it("gives the Ver fila drawer the active version's source fields", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [make(1, "aplicada")],
    });
    vi.mocked(listRows).mockResolvedValue({
      ok: true,
      data: {
        items: [{ source_row_number: 2 }] as never,
        next_cursor: null,
        has_more: false,
        total_count: 1,
      },
    });
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage sourceFields={["estado_resumido", "numero_ingreso"]} />
      </RouterProvider>,
    );
    const row = await screen.findByTestId("override-1");
    await userEvent.click(
      within(row).getByRole("button", { name: "Ver fila" }),
    );
    expect(await screen.findByTestId("drawer")).toHaveAttribute(
      "data-source-fields",
      "estado_resumido,numero_ingreso",
    );
  });

  it("says so when Ver fila finds no such row", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [make(1, "aplicada")],
    });
    vi.mocked(listRows).mockResolvedValue({
      ok: true,
      data: { items: [], next_cursor: null, has_more: false, total_count: 0 },
    });
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    );
    const row = await screen.findByTestId("override-1");
    await userEvent.click(
      within(row).getByRole("button", { name: "Ver fila" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No se encontró la fila",
    );
    expect(screen.queryByTestId("drawer")).toBeNull();
  });

  it("titles a failed load as about the edits, not the import", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: false,
      status: 500,
      error: "boom",
    });
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    );
    expect(
      await screen.findByText("No se pudieron cargar las ediciones web"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/importación no se completó/i)).toBeNull();
  });

  it("explains the decision only when something needs one", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [make(1, "aplicada")],
    });
    const { unmount } = render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    );
    await screen.findByTestId("overrides-table");
    expect(screen.queryByTestId("conflict-help")).toBeNull();
    unmount();

    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [make(1, "en_conflicto")],
    });
    render(
      <RouterProvider initialPath="/transelec/ediciones">
        <EdicionesPage />
      </RouterProvider>,
    );
    expect(await screen.findByTestId("conflict-help")).toHaveTextContent(
      "«Mantener valor web» vuelve a mostrar el valor web",
    );
  });

  describe("download", () => {
    const renderPane = async () => {
      vi.mocked(listOverrides).mockResolvedValue({
        ok: true,
        data: [make(1, "aplicada")],
      });
      render(
        <RouterProvider initialPath="/transelec/ediciones">
          <EdicionesPage />
        </RouterProvider>,
      );
      return screen.findByTestId("download-xlsx");
    };

    it("saves the blob under the server's file name while showing a busy state", async () => {
      const createUrl = vi.fn(() => "blob:planilla");
      const revokeUrl = vi.fn();
      vi.stubGlobal(
        "URL",
        Object.assign(URL, {
          createObjectURL: createUrl,
          revokeObjectURL: revokeUrl,
        }),
      );
      const clicks: string[] = [];
      const click = vi
        .spyOn(HTMLAnchorElement.prototype, "click")
        .mockImplementation(function (this: HTMLAnchorElement) {
          clicks.push(this.download);
        });
      let finish!: (
        value: Awaited<ReturnType<typeof downloadOverridesXlsx>>,
      ) => void;
      vi.mocked(downloadOverridesXlsx).mockReturnValue(
        new Promise((resolve) => {
          finish = resolve;
        }),
      );
      const button = await renderPane();
      await userEvent.click(button);
      // aria-disabled, so the button keeps keyboard focus while busy.
      expect(button).toHaveAttribute("aria-disabled", "true");
      expect(button).toHaveFocus();
      expect(button).toHaveTextContent("Preparando la planilla…");
      expect(screen.getByTestId("edits-status")).toHaveTextContent(
        "Preparando la planilla…",
      );
      await userEvent.click(button); // a second press while busy does nothing
      expect(downloadOverridesXlsx).toHaveBeenCalledTimes(1);

      finish({
        ok: true,
        data: { blob: new Blob(["x"]), filename: "planilla ediciones.xlsx" },
      });
      await waitFor(() =>
        expect(button).toHaveAttribute("aria-disabled", "false"),
      );
      expect(button).toHaveFocus();
      expect(screen.getByTestId("edits-status")).toBeEmptyDOMElement();
      expect(clicks).toEqual(["planilla ediciones.xlsx"]);
      expect(createUrl).toHaveBeenCalledTimes(1);
      // Revoked after the click has been handled, not in the same tick.
      await waitFor(() =>
        expect(revokeUrl).toHaveBeenCalledWith("blob:planilla"),
      );
      expect(screen.queryByText("No se pudo descargar la planilla")).toBeNull();
      click.mockRestore();
      vi.unstubAllGlobals();
    });

    it.each([
      [
        409,
        "Esta versión se importó sin el mapa de columnas; vuelva a importar.",
      ],
      [
        422,
        "No se pudo preparar la planilla con ediciones. Contacte a soporte.",
      ],
    ])("shows the server's message for a %s", async (status, error) => {
      vi.mocked(downloadOverridesXlsx).mockResolvedValue({
        ok: false,
        status,
        error,
      });
      const button = await renderPane();
      await userEvent.click(button);
      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("No se pudo descargar la planilla");
      expect(alert).toHaveTextContent(error);
      expect(button).toHaveAttribute("aria-disabled", "false");
    });

    it("shows the server's detail for a 404", async () => {
      vi.mocked(downloadOverridesXlsx).mockResolvedValue({
        ok: false,
        status: 404,
        error: "No hay una versión publicada.",
        payload: { detail: "No hay una versión publicada." },
      });
      await userEvent.click(await renderPane());
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "No hay una versión publicada.",
      );
    });

    it("explains a 403 in Spanish rather than the server's English text", async () => {
      vi.mocked(downloadOverridesXlsx).mockResolvedValue({
        ok: false,
        status: 403,
        error: "Forbidden",
        payload: { detail: "Forbidden" },
      });
      await userEvent.click(await renderPane());
      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("Su cuenta no tiene permisos");
      expect(alert).not.toHaveTextContent("Forbidden");
    });

    it("uses fixed copy for a 5xx without a JSON payload", async () => {
      vi.mocked(downloadOverridesXlsx).mockResolvedValue({
        ok: false,
        status: 502,
        error: "Bad Gateway",
      });
      await userEvent.click(await renderPane());
      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(
        "La plataforma no pudo preparar la planilla. Intente de nuevo; si se repite, contacte a soporte.",
      );
      expect(alert).not.toHaveTextContent("Bad Gateway");
    });
  });
});
