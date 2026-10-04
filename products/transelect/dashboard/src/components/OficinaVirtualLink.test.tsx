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

  it("offers no copy button without an N.º", () => {
    render(<OficinaVirtualLink numero={null} />);
    expect(screen.queryByTestId("oficina-virtual-copy")).toBeNull();
  });
});
