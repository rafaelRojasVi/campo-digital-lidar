import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RowDetailDrawer } from "./RowDetailDrawer";
import { makeLifecycleRow, makeRow } from "../test/factories";
import type { AefPmf, AefPmfField, TranselecAef } from "../api";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, getPmfDetail: vi.fn(), getAef: vi.fn() };
});

const { getPmfDetail, getAef } = await import("../api");

const tracked = makeRow({
  source_row_number: 2,
  pmf: "BN001",
  aef: "Presentado",
});
const untracked = makeRow({ source_row_number: 3, pmf: "BN001" });
const blank: AefPmfField = {
  status: "blank",
  value: null,
  value_kind: null,
  source_rows: [],
  variants: [],
};
const pmfTracking: AefPmf = {
  pmf: "BN001",
  total_rows: 2,
  rows_with_any_tracking: 1,
  rows_with_aef: 1,
  source_row_numbers: [2, 3],
  has_conflict: false,
  chronology_flags: [],
  fields: {
    aef: {
      status: "value",
      value: "Presentado",
      value_kind: "text",
      source_rows: [2],
      variants: [],
    },
    quien_solicita: blank,
    fecha_solicitud: blank,
    fecha_corta: blank,
    fecha_termino: blank,
  },
};

describe("RowDetailDrawer — AEF section", () => {
  beforeEach(() => {
    vi.mocked(getPmfDetail).mockReset();
    vi.mocked(getAef).mockReset();
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: { pmfs: [pmfTracking] } as unknown as TranselecAef,
    });
    vi.mocked(getPmfDetail).mockResolvedValue({
      ok: true,
      data: {
        pmf: "BN001",
        row_count: 2,
        basis_estado_resumido: "estado_resumido_first_row",
        estado_resumido: "Aprobado",
        rows: [tracked, untracked],
      },
    });
  });

  it("shows a blank row as blank and points to the PMF row that holds the value", async () => {
    render(
      <RowDetailDrawer
        row={untracked}
        onClose={() => {}}
        sourceFields={["aef", "pmf"]}
      />,
    );

    expect(screen.getByTestId("drawer-aef")).toHaveTextContent(
      "AEF de esta fila de origen",
    );
    expect(screen.getByTestId("drawer-aef")).toHaveTextContent(
      "AEFSin registro en esta fila",
    );
    await waitFor(() =>
      expect(screen.getByTestId("drawer-pmf-aef-rows")).toHaveTextContent(
        "Todos los valores de este PMF vienen de la fila 2 de la hoja «Resumen».",
      ),
    );
    expect(screen.getByTestId("drawer-pmf-aef")).toHaveTextContent(
      "AEFPresentado",
    );
    expect(screen.getByTestId("drawer-pmf-aef")).not.toHaveTextContent(
      "· fila",
    );
    await waitFor(() =>
      expect(screen.getByTestId("drawer-aef-coverage")).toHaveTextContent(
        "1 de 2 filas de BN001 tienen registro AEF. El seguimiento de este PMF está en la fila 2; esta fila no lo repite y se muestra vacía, como en la planilla.",
      ),
    );
  });

  it("names each value's source row when the PMF's values come from different rows", async () => {
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: {
        pmfs: [
          {
            ...pmfTracking,
            fields: {
              ...pmfTracking.fields,
              quien_solicita: {
                status: "value",
                value: "Persona Sintética",
                value_kind: "text",
                source_rows: [3],
                variants: [],
              },
            },
          },
        ],
      } as unknown as TranselecAef,
    });
    render(
      <RowDetailDrawer
        row={untracked}
        onClose={() => {}}
        sourceFields={["aef", "pmf"]}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("drawer-pmf-aef")).toHaveTextContent(
        "AEFPresentadofila 2",
      ),
    );
    expect(screen.getByTestId("drawer-pmf-aef")).toHaveTextContent(
      "Persona Sintéticafila 3",
    );
    expect(screen.queryByTestId("drawer-pmf-aef-rows")).not.toBeInTheDocument();
  });

  it("says the published workbook has no AEF columns rather than implying blanks", () => {
    render(
      <RowDetailDrawer
        row={untracked}
        onClose={() => {}}
        sourceFields={["pmf"]}
      />,
    );

    expect(screen.getByTestId("drawer-aef")).toHaveTextContent(
      "La planilla publicada no incluye las columnas de seguimiento AEF",
    );
    expect(
      screen.queryByText("Sin registro en esta fila"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("drawer-pmf-aef")).not.toBeInTheDocument();
    expect(getAef).not.toHaveBeenCalled();
  });

  it("does not choose between conflicting PMF AEF values", async () => {
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: {
        pmfs: [
          {
            ...pmfTracking,
            has_conflict: true,
            fields: {
              ...pmfTracking.fields,
              aef: {
                status: "conflict",
                value: null,
                value_kind: null,
                source_rows: [],
                variants: [
                  { value: "Presentado", source_rows: [2] },
                  { value: "Solicitado", source_rows: [3] },
                ],
              },
            },
          },
        ],
      } as unknown as TranselecAef,
    });
    render(
      <RowDetailDrawer
        row={untracked}
        onClose={() => {}}
        sourceFields={["aef", "pmf"]}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("drawer-pmf-aef")).toHaveTextContent(
        "Valores distintos; requiere revisión",
      ),
    );
    expect(screen.getByTestId("drawer-pmf-aef")).toHaveTextContent(
      "Presentado · fila 2",
    );
    expect(screen.getByTestId("drawer-pmf-aef")).toHaveTextContent(
      "Solicitado · fila 3",
    );
    expect(screen.getByTestId("drawer-aef")).toHaveTextContent(
      "Sin registro en esta fila",
    );
  });

  it("shows the raw text of a date cell, and marks unresolved text as not a date", () => {
    const row = makeRow({
      source_row_number: 4,
      pmf: "BN001",
      fecha_ingreso: "2024-11-13",
      fecha_90_dias: null,
      source_text_dates: {
        fecha_ingreso: {
          raw: "13 de noviembre de 2024",
          resolution: "parsed_spanish_long",
          parsed: "2024-11-13",
        },
        fecha_90_dias: {
          raw: "28-04-2025 28-09-26",
          resolution: "multiple_dates",
          parsed: null,
        },
      },
    });
    render(
      <RowDetailDrawer
        row={row}
        onClose={() => {}}
        sourceFields={["aef", "pmf"]}
      />,
    );

    expect(
      screen.getByText("Fecha escrita en texto: «13 de noviembre de 2024»"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("13-11-2024", { exact: false }),
    ).toBeInTheDocument();
    expect(screen.getByText("28-04-2025 28-09-26")).toBeInTheDocument();
    expect(screen.getByText("Varias fechas en la celda")).toBeInTheDocument();
  });
});

describe("RowDetailDrawer — second ingreso (30-Sept-2026 layout)", () => {
  beforeEach(() => {
    vi.mocked(getPmfDetail).mockReset();
    vi.mocked(getAef).mockReset();
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: { pmfs: [] } as unknown as TranselecAef,
    });
    vi.mocked(getPmfDetail).mockResolvedValue({
      ok: true,
      data: {
        pmf: "BN001",
        row_count: 1,
        basis_estado_resumido: "estado_resumido_first_row",
        estado_resumido: "En tramite",
        rows: [untracked],
      },
    });
  });

  it("shows both ingresos side by side, with the raw text of a two-date cell", () => {
    const row = makeRow({
      source_row_number: 5,
      pmf: "BN001",
      numero_ingreso: "ING-1",
      fecha_ingreso: "2024-04-17",
      numero_ingreso_2: "ING-1-R",
      fecha_ingreso_2: null,
      source_text_dates: {
        fecha_ingreso_2: {
          raw: "20-12-2024 09-06-26",
          resolution: "multiple_dates",
          parsed: null,
        },
      },
    });
    render(
      <RowDetailDrawer
        row={row}
        onClose={() => {}}
        sourceFields={[
          "pmf",
          "numero_ingreso",
          "fecha_ingreso_2",
          "numero_ingreso_2",
        ]}
      />,
    );

    expect(screen.getByTestId("drawer-numero-ingreso-2")).toHaveTextContent(
      "ING-1-R",
    );
    expect(screen.getByTestId("drawer-fecha-ingreso-2")).toHaveTextContent(
      "20-12-2024 09-06-26",
    );
    expect(screen.getByTestId("drawer-fecha-ingreso-2")).toHaveTextContent(
      "Varias fechas en la celda",
    );
    expect(screen.queryByTestId("drawer-ingreso-2-absent")).toBeNull();
  });

  it("says a blank second ingreso is blank when the source had the columns", () => {
    render(
      <RowDetailDrawer
        row={makeRow({ pmf: "BN001" })}
        onClose={() => {}}
        sourceFields={["pmf", "fecha_ingreso_2", "numero_ingreso_2"]}
      />,
    );

    expect(screen.getByTestId("drawer-numero-ingreso-2")).toHaveTextContent(
      "Sin segundo ingreso",
    );
    expect(screen.getByTestId("drawer-fecha-ingreso-2")).toHaveTextContent(
      "Sin fecha",
    );
  });

  it('states that the published workbook has no second-ingreso columns instead of "sin ingreso"', () => {
    render(
      <RowDetailDrawer
        row={makeRow({ pmf: "BN001" })}
        onClose={() => {}}
        sourceFields={["pmf", "aef"]}
      />,
    );

    expect(screen.getByTestId("drawer-ingreso-2-absent")).toHaveTextContent(
      "Fecha de ingreso2",
    );
    expect(screen.queryByTestId("drawer-numero-ingreso-2")).toBeNull();
    expect(screen.queryByText("Sin segundo ingreso")).toBeNull();
  });
});

describe("RowDetailDrawer — Proceso CONAF (lifecycle_pmf_v1)", () => {
  beforeEach(() => {
    vi.mocked(getPmfDetail).mockReset();
    vi.mocked(getAef).mockReset();
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: { pmfs: [] } as unknown as TranselecAef,
    });
    vi.mocked(getPmfDetail).mockResolvedValue({
      ok: true,
      data: {
        pmf: "MP002",
        row_count: 1,
        basis_estado_resumido: "estado_resumido_first_row",
        estado_resumido: "En tramite",
        rows: [makeRow({ source_row_number: 3, pmf: "MP002" })],
      },
    });
  });

  it("shows where the PMF stands when the Estado section opens it", () => {
    const lifecycle = makeLifecycleRow({
      source_row_number: 3,
      pmf: "MP002",
      lifecycle_step: "rechazado_esperando_recurso",
    });
    render(<RowDetailDrawer row={lifecycle} lifecycle={lifecycle} onClose={() => {}} />);

    const block = screen.getByTestId("drawer-lifecycle");
    expect(block).toHaveTextContent("En trámite");
    expect(block).toHaveTextContent("Rechazado, esperando recurso");
    expect(block).toHaveTextContent("primera fila del PMF (fila 3)");
    expect(block).toHaveTextContent("provisional");
  });

  it("says why a PMF is unclassified and that its rows disagree", () => {
    const lifecycle = makeLifecycleRow({
      source_row_number: 3,
      pmf: "MP002",
      lifecycle_group: "sin_clasificar",
      lifecycle_step: null,
      lifecycle_reason: "estado_y_resumido_no_coinciden",
      lifecycle_flags: ["filas_no_coinciden"],
    });
    render(<RowDetailDrawer row={lifecycle} lifecycle={lifecycle} onClose={() => {}} />);

    const block = screen.getByTestId("drawer-lifecycle");
    expect(block).toHaveTextContent("Sin clasificar");
    expect(block).toHaveTextContent("«Estado» y «Estado resumido» no coinciden");
    expect(block).toHaveTextContent("Sus filas no tienen el mismo");
    // The reason is the «Para revisar» fact; it is not stated a second time as a hint.
    expect(block.textContent?.match(/«Estado» y «Estado resumido» no coinciden/g) ?? []).toHaveLength(1);
    expect(within(block).getByText("Para revisar en la planilla")).toBeInTheDocument();
    expect(within(block).queryByText("Paso")).toBeNull();
  });

  it.each([
    ["aprobado", "Aprobado"],
    ["descartado", "Descartado"],
  ] as const)("labels a closed %s PMF «Paso», not «Para revisar»", (group, text) => {
    const lifecycle = makeLifecycleRow({
      lifecycle_group: group,
      lifecycle_step: null,
      lifecycle_reason: null,
    });
    render(<RowDetailDrawer row={lifecycle} lifecycle={lifecycle} onClose={() => {}} />);
    const block = screen.getByTestId("drawer-lifecycle");
    expect(block).toHaveTextContent(text);
    expect(within(block).getByText("Paso")).toBeInTheDocument();
    expect(within(block).queryByText("Para revisar en la planilla")).toBeNull();
  });

  it("has no Proceso CONAF block from elsewhere, but always links the Oficina Virtual", () => {
    render(
      <RowDetailDrawer
        row={makeRow({ source_row_number: 3, pmf: "MP002", numero_ingreso: "ING-7" })}
        onClose={() => {}}
      />,
    );

    expect(screen.queryByTestId("drawer-lifecycle")).toBeNull();
    const link = screen.getByTestId("drawer-ov-1-link");
    expect(link).toHaveAttribute("href", "https://oficinavirtual.conaf.cl/consultas/index.php");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAccessibleName(/pestaña nueva/);
    expect(screen.getByTestId("drawer-ov-1-copy")).toHaveAccessibleName("Copiar N.º ING-7");
  });

  it("copies the N.º and says so", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    try {
      render(
        <RowDetailDrawer
          row={makeRow({ source_row_number: 3, pmf: "MP002", numero_ingreso: "ING-7" })}
          onClose={() => {}}
        />,
      );
      screen.getByTestId("drawer-ov-1-copy").click();

      await waitFor(() => expect(screen.getByText("N.º copiado.")).toBeInTheDocument());
      expect(writeText).toHaveBeenCalledWith("ING-7");
      expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("still closes with Escape pressed on the Oficina Virtual link", () => {
    const onClose = vi.fn();
    render(
      <RowDetailDrawer
        row={makeRow({ source_row_number: 3, pmf: "MP002", numero_ingreso: "ING-7" })}
        onClose={onClose}
      />,
    );
    fireEvent.keyDown(screen.getByTestId("drawer-ov-1-link"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
