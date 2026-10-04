import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RouterProvider } from "../router";
import { WebEditConflicts } from "./WebEditConflicts";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, listOverrides: vi.fn() };
});

const { listOverrides } = await import("../api");

const entry = (id: number, status: string) => ({ id, status });

function renderBlock(canEdit = true) {
  return render(
    <RouterProvider initialPath="/transelec/calidad">
      <WebEditConflicts canEdit={canEdit} />
    </RouterProvider>,
  );
}

describe("WebEditConflicts", () => {
  beforeEach(() => vi.mocked(listOverrides).mockReset());

  it("shows the counts and a link to the pane", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [
        entry(1, "en_conflicto"),
        entry(2, "huerfana"),
        entry(3, "aplicada"),
      ] as never,
    });
    renderBlock();
    expect(
      await screen.findByText("Ediciones web en conflicto"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ediciones web/ })).toHaveAttribute(
      "href",
      "/transelec/ediciones",
    );
  });

  it("renders nothing when there are no conflicts or the read fails", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [entry(3, "aplicada")] as never,
    });
    const { container } = renderBlock();
    await waitFor(() => expect(listOverrides).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
    vi.mocked(listOverrides).mockResolvedValue({
      ok: false,
      status: 500,
      error: "x",
    });
    const failed = renderBlock();
    await waitFor(() => expect(listOverrides).toHaveBeenCalledTimes(2));
    expect(failed.container).toBeEmptyDOMElement();
  });

  it("words only the non-zero counts, in the singular when it is one", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [entry(1, "en_conflicto")] as never,
    });
    const { container } = renderBlock();
    await screen.findByText("Ediciones web en conflicto");
    expect(container).toHaveTextContent(
      "1 edición difiere de la planilla publicada.",
    );
    expect(container).not.toHaveTextContent("0");

    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [entry(2, "huerfana"), entry(3, "huerfana")] as never,
    });
    const orphans = renderBlock();
    await waitFor(() =>
      expect(orphans.container).toHaveTextContent(
        "2 ediciones ya no tienen fila en la planilla publicada.",
      ),
    );
  });

  it("offers no link to someone who cannot edit", async () => {
    vi.mocked(listOverrides).mockResolvedValue({
      ok: true,
      data: [entry(1, "en_conflicto")] as never,
    });
    renderBlock(false);
    await screen.findByText("Ediciones web en conflicto");
    expect(screen.queryByRole("link")).toBeNull();
  });
});
