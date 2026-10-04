import { render, screen, within } from "@testing-library/react";
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
  };
});

vi.mock("../components/RowDetailDrawer", () => ({
  RowDetailDrawer: ({ row }: { row: { source_row_number: number } }) => (
    <div data-testid="drawer">fila {row.source_row_number}</div>
  ),
}));

const { listOverrides, keepOverride, discardOverride, listRows } =
  await import("../api");

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

    expect(await screen.findByTestId("download-xlsx")).toHaveAttribute(
      "href",
      "/api/transelec/export.xlsx",
    );
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
});
