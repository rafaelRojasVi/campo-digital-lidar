import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OficinaVirtualLink } from "./OficinaVirtualLink";

describe("OficinaVirtualLink keyboard and click isolation", () => {
  it("keeps Enter and Space from reaching a clickable row, but lets other keys through", () => {
    const onRowKey = vi.fn();
    const onRowClick = vi.fn();
    render(
      <div onKeyDown={onRowKey} onClick={onRowClick}>
        <OficinaVirtualLink numero="ING-7" compact />
      </div>,
    );
    const link = screen.getByTestId("oficina-virtual-link");

    fireEvent.keyDown(link, { key: "Enter" });
    fireEvent.keyDown(link, { key: " " });
    expect(onRowKey).not.toHaveBeenCalled();

    fireEvent.keyDown(link, { key: "Tab" });
    fireEvent.keyDown(link, { key: "Escape" });
    expect(onRowKey).toHaveBeenCalledTimes(2);

    fireEvent.click(link);
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("opens CONAF's result for a plain N.º, with the number already entered", () => {
    render(<OficinaVirtualLink numero=" 123456 " />);
    expect(screen.getByTestId("oficina-virtual-link")).toHaveAttribute(
      "href",
      "https://oficinavirtual.conaf.cl/consultas/action.php?nsolicitud=123456",
    );
  });

  it("opens the empty consulta page for a planilla-style N.º CONAF cannot answer", () => {
    // CONAF answers «No fue posible realizar su consulta» to «n/n-n/n».
    render(<OficinaVirtualLink numero="12/34-5/26" />);
    expect(screen.getByTestId("oficina-virtual-link")).toHaveAttribute(
      "href",
      "https://oficinavirtual.conaf.cl/consultas/index.php",
    );
    expect(screen.getByTestId("oficina-virtual-copy")).toBeInTheDocument();
  });

  it("opens CONAF's empty consulta page without an N.º", () => {
    render(<OficinaVirtualLink numero={null} />);
    expect(screen.getByTestId("oficina-virtual-link")).toHaveAttribute(
      "href",
      "https://oficinavirtual.conaf.cl/consultas/index.php",
    );
  });

  it("offers no copy button without an N.º", () => {
    render(<OficinaVirtualLink numero={null} />);
    expect(screen.queryByTestId("oficina-virtual-copy")).toBeNull();
  });
});
