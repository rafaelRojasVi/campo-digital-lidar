/**
 * Web edits (`docs/superpowers/specs/2026-10-04-transelec-web-edits-xlsx-design.md` §6):
 * edit from the drawer, the 409 path, what a viewer sees, the Datos pane and
 * the Calidad block. The API is stubbed; the server-side rules have their own
 * integration tests. The stub keeps the edits in memory so the drawer's
 * refetch after a save or a revert sees what a real server would return.
 */
import { expect, test } from "@playwright/test";
import type { Page, Route } from "@playwright/test";
import { makeApiRow, stubPlatform } from "./stubs";
import type { StubOptions } from "./stubs";

type Override = Record<string, unknown> & {
  id: number;
  field: string;
  pmf: string;
};

const BASE_OVERRIDE = {
  field: "estado_resumido",
  field_label: "Estado resumido",
  status: "aplicada",
  pmf: "PMF-001",
  rol: "101-1",
  numero_predio: "10",
  numero_area_corta: "A1",
  source_row_number: 1,
  web_value: "Aprobado",
  planilla_value_at_edit: "En tramite",
  planilla_value_now: "En tramite",
  created_by_display_name: "Dev Admin",
  created_at: "2026-10-04T15:00:00+00:00",
};

const VIEWER = {
  identity_key: "dev-viewer",
  display_name: "Dev Viewer",
  product_grants: [{ product_key: "transelect", role: "viewer" }],
};

function fulfill(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: status === 204 ? undefined : JSON.stringify(body),
  });
}

/** Row 1 as the stub serves it, with the in-memory edits applied. */
function rowWith(edits: Override[], index = 1) {
  const mine = edits.filter((entry) => entry.source_row_number === index);
  return makeApiRow(index, {
    ...Object.fromEntries(mine.map((entry) => [entry.field, entry.web_value])),
    web_fields: mine.map((entry) => entry.field),
  });
}

/**
 * A stateful stand-in for the override routes: PUT stores the edit, ending
 * any earlier edit of the same cell as the server does; DELETE removes it;
 * and the list, the PMF detail and the rows list all reflect it.
 */
function statefulEdits(edits: Override[], saves: unknown[] = []): StubOptions {
  // Above any seeded edit, so ids stay unique as they are on the server.
  let nextId = Math.max(30, ...edits.map((entry) => entry.id)) + 1;
  return {
    rowOverrides: (index) => {
      const { estado_resumido, web_fields } = rowWith(edits, index) as Record<
        string,
        unknown
      >;
      return { estado_resumido, web_fields };
    },
    extra: async (page: Page) => {
      await page.route("**/api/transelec/pmfs/*", (route) => {
        const pmf = decodeURIComponent(
          new URL(route.request().url()).pathname.split("/").pop() ?? "",
        );
        const index = Number(pmf.replace(/\D/g, "")) || 1;
        return fulfill(route, {
          pmf,
          row_count: 1,
          basis_estado_resumido: "estado_resumido_first_row",
          estado_resumido: rowWith(edits, index).estado_resumido,
          rows: [rowWith(edits, index)],
        });
      });
      await page.route("**/api/transelec/overrides*", async (route) => {
        const request = route.request();
        if (request.method() === "PUT") {
          const body = request.postDataJSON();
          saves.push(body);
          const entry: Override = {
            ...BASE_OVERRIDE,
            id: nextId++,
            field: body.field,
            web_value: body.value,
            planilla_value_at_edit: body.expected_value,
            source_row_number: body.source_row_number,
          };
          const same = edits.findIndex(
            (other) =>
              other.field === entry.field &&
              other.source_row_number === entry.source_row_number,
          );
          if (same >= 0) edits.splice(same, 1);
          edits.push(entry);
          return fulfill(route, {
            override_id: entry.id,
            changed: true,
            row: rowWith(edits, body.source_row_number),
          });
        }
        return fulfill(route, edits);
      });
      await page.route("**/api/transelec/overrides/**", (route) => {
        const id = Number(
          new URL(route.request().url()).pathname.split("/").pop(),
        );
        const at = edits.findIndex((entry) => entry.id === id);
        if (route.request().method() === "DELETE" && at >= 0)
          edits.splice(at, 1);
        return fulfill(route, {}, 204);
      });
    },
  };
}

async function openFirstRow(page: Page) {
  await page.goto("/transelec/explorador");
  await page.getByTestId("row-1").click();
  const drawer = page.getByTestId("row-drawer");
  await expect(drawer.getByTestId("drawer-editables")).toBeVisible();
  return drawer;
}

test("an operator edits Estado resumido from the drawer and sees the «web» chip and who edited", async ({
  page,
}) => {
  const saves: unknown[] = [];
  await stubPlatform(page, statefulEdits([], saves));

  const drawer = await openFirstRow(page);
  const field = drawer.getByTestId("editable-estado_resumido");
  await expect(field.getByTestId("web-chip")).toHaveCount(0);
  await field.getByRole("button", { name: "Editar Estado resumido" }).click();
  await drawer.getByLabel("Nuevo valor de Estado resumido").fill("Aprobado");
  await drawer.getByRole("button", { name: "Guardar" }).click();

  await expect(drawer.getByTestId("editables-status")).toContainText(
    "Se guardó el cambio en Estado resumido.",
  );
  await expect(field.getByTestId("web-chip")).toBeVisible();
  await expect(field).toContainText("Aprobado");
  await expect(drawer.getByTestId("provenance-estado_resumido")).toContainText(
    "Editado en la web por Dev Admin",
  );
  expect(saves).toEqual([
    {
      import_id: 7,
      source_row_number: 1,
      field: "estado_resumido",
      value: "Aprobado",
      expected_value: "En tramite",
    },
  ]);
});

test("reverting an edit asks for confirmation and brings back the planilla value", async ({
  page,
}) => {
  await stubPlatform(page, statefulEdits([{ ...BASE_OVERRIDE, id: 31 }]));

  const drawer = await openFirstRow(page);
  const field = drawer.getByTestId("editable-estado_resumido");
  await expect(field.getByTestId("web-chip")).toBeVisible();
  await field
    .getByRole("button", {
      name: "Volver al valor de la planilla de Estado resumido",
    })
    .click();
  await page
    .getByRole("dialog", { name: "Volver al valor de la planilla" })
    .getByRole("button", { name: "Volver al valor de la planilla" })
    .click();

  await expect(drawer.getByTestId("editables-status")).toContainText(
    "Estado resumido volvió al valor de la planilla.",
  );
  await expect(field.getByTestId("web-chip")).toHaveCount(0);
  await expect(field).toContainText("En tramite");
});

test("a concurrent change is explained, offers Recargar, and nothing is overwritten", async ({
  page,
}) => {
  const edits: Override[] = [];
  await stubPlatform(page, {
    ...statefulEdits(edits),
    extra: async (p) => {
      await statefulEdits(edits).extra?.(p);
      await p.route("**/api/transelec/overrides*", async (route) => {
        if (route.request().method() !== "PUT")
          return route.fulfill({
            status: 200,
            contentType: "application/json",
            body: "[]",
          });
        await fulfill(
          route,
          { detail: "El valor cambió.", code: "value_changed" },
          409,
        );
      });
    },
  });

  const drawer = await openFirstRow(page);
  await drawer.getByRole("button", { name: "Editar Estado resumido" }).click();
  await drawer.getByLabel("Nuevo valor de Estado resumido").fill("Aprobado");
  await drawer.getByRole("button", { name: "Guardar" }).click();

  await expect(drawer.getByRole("alert")).toContainText(
    "Otra persona cambió este valor",
  );
  await expect(drawer.getByRole("button", { name: "Recargar" })).toBeVisible();
  await expect(
    drawer.getByTestId("editable-estado_resumido").getByTestId("web-chip"),
  ).toHaveCount(0);
  expect(edits).toEqual([]);
});

test("Escape cancels the editor without closing the drawer", async ({
  page,
}) => {
  await stubPlatform(page, statefulEdits([]));

  const drawer = await openFirstRow(page);
  await drawer.getByRole("button", { name: "Editar Estado resumido" }).click();
  const input = drawer.getByLabel("Nuevo valor de Estado resumido");
  await expect(input).toBeFocused();
  await page.keyboard.press("Escape");

  await expect(input).toHaveCount(0);
  await expect(drawer).toBeVisible();
  await expect(
    drawer.getByRole("button", { name: "Editar Estado resumido" }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
});

test("a viewer sees the chip and who edited, but no edit controls", async ({
  page,
}) => {
  await stubPlatform(page, {
    ...statefulEdits([{ ...BASE_OVERRIDE, id: 31 }]),
    me: VIEWER,
  });

  await page.goto("/transelec/explorador");
  await expect(page.getByTestId("row-1").getByTestId("web-chip")).toBeVisible();
  await page.getByTestId("row-1").click();
  const drawer = page.getByTestId("row-drawer");
  const field = drawer.getByTestId("editable-estado_resumido");
  await expect(field.getByTestId("web-chip")).toBeVisible();
  await expect(drawer.getByTestId("provenance-estado_resumido")).toContainText(
    /Editado en la web por Dev Admin · 04-10-2026/,
  );
  await expect(drawer.getByRole("button", { name: /^Editar/ })).toHaveCount(0);
  await expect(
    drawer.getByRole("button", { name: /^Volver al valor/ }),
  ).toHaveCount(0);
});

test("the Estado drawer edits too, and Estado re-reads the PMF after a save", async ({
  page,
}) => {
  await stubPlatform(page, statefulEdits([]));
  let lifecycleReads = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/transelec/lifecycle"))
      lifecycleReads += 1;
  });

  await page.goto("/transelec/estado");
  await page.getByTestId("estado-row-1").locator("td").first().click();
  const drawer = page.getByTestId("row-drawer");
  await drawer.getByRole("button", { name: "Editar Estado resumido" }).click();
  await drawer.getByLabel("Nuevo valor de Estado resumido").fill("Aprobado");
  const readsBeforeSave = lifecycleReads;
  await drawer.getByRole("button", { name: "Guardar" }).click();

  await expect(drawer.getByTestId("editables-status")).toContainText(
    "Se guardó el cambio en Estado resumido.",
  );
  await expect.poll(() => lifecycleReads).toBeGreaterThan(readsBeforeSave);
  await expect(drawer).toBeVisible();
});

test("Datos → Ediciones web lists conflicts first, keeps only on conflicts, and offers the download", async ({
  page,
}) => {
  const edits: Override[] = [
    { ...BASE_OVERRIDE, id: 30, pmf: "PMF-002", source_row_number: 2 },
    {
      ...BASE_OVERRIDE,
      id: 31,
      status: "en_conflicto",
      planilla_value_now: "Desistido",
    },
  ];
  let kept = false;
  await stubPlatform(page, {
    extra: async (p) => {
      await p.route("**/api/transelec/export.xlsx", (route) =>
        route.fulfill({
          status: 200,
          contentType:
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          headers: {
            "Content-Disposition":
              "attachment; filename=\"planilla_con_ediciones.xlsx\"",
          },
          body: "xlsx",
        }),
      );
      await p.route("**/api/transelec/overrides*", (route) =>
        fulfill(route, edits),
      );
      await p.route("**/api/transelec/overrides/**", (route) => {
        if (
          route.request().method() === "POST" &&
          route.request().url().endsWith("/31/keep")
        ) {
          kept = true;
          edits[1] = { ...edits[1], status: "aplicada" };
          return fulfill(route, { override_id: 32 });
        }
        return fulfill(route, {}, 404);
      });
    },
  });

  await page.goto("/transelec/ediciones");
  const download = page.waitForEvent("download");
  await page.getByTestId("download-xlsx").click();
  expect((await download).suggestedFilename()).toBe(
    "planilla_con_ediciones.xlsx",
  );
  const rows = page.getByTestId("overrides-table").locator("tbody tr");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toHaveAttribute("data-testid", "override-31");
  await expect(rows.nth(1)).toHaveAttribute("data-testid", "override-30");

  const conflict = page.getByTestId("override-31");
  await expect(conflict).toContainText("En conflicto con la planilla");
  await expect(conflict).toContainText("Desistido");
  await expect(
    page
      .getByTestId("override-30")
      .getByRole("button", { name: "Mantener valor web" }),
  ).toHaveCount(0);

  await conflict.getByRole("button", { name: "Mantener valor web" }).click();
  await expect.poll(() => kept).toBe(true);
  await expect(page.getByTestId("edits-status")).toContainText(
    "Se mantuvo el valor web",
  );
  await expect(
    page.getByRole("button", { name: "Mantener valor web" }),
  ).toHaveCount(0);
});

test("Datos → Ediciones web has no horizontal page scroll at 390 px", async ({
  page,
}) => {
  await stubPlatform(page, {
    extra: async (p) => {
      await p.route("**/api/transelec/overrides*", (route) =>
        fulfill(route, [
          {
            ...BASE_OVERRIDE,
            id: 31,
            status: "en_conflicto",
            planilla_value_now: "Desistido",
          },
        ]),
      );
    },
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/transelec/ediciones");
  await expect(page.getByTestId("override-31")).toBeVisible();
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);
});

for (const width of [390, 1280]) {
  test(`Explorador with «web» chips has no horizontal page scroll at ${width} px`, async ({
    page,
  }) => {
    await stubPlatform(page, {
      rowOverrides: () => ({
        numero_ingreso: "2026-0042",
        web_fields: ["numero_ingreso"],
      }),
    });
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/transelec/explorador");
    await expect(page.getByTestId("row-1")).toBeVisible();
    await expect(page.getByTestId("web-chip").first()).toBeAttached();
    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);
  });
}

test("Calidad shows the web-edit conflicts block with a link to the pane", async ({
  page,
}) => {
  await stubPlatform(page, {
    extra: async (p) => {
      await p.route("**/api/transelec/overrides*", (route) =>
        fulfill(route, [{ ...BASE_OVERRIDE, id: 31, status: "en_conflicto" }]),
      );
    },
  });
  await page.goto("/transelec/calidad");
  const block = page.getByTestId("web-edit-conflicts");
  await expect(block).toContainText("1 edición difiere");
  await block.getByRole("link", { name: /Ediciones web/ }).click();
  await expect(page).toHaveURL(/\/transelec\/ediciones$/);
});

test("Calidad hides the block when no edit is in conflict", async ({
  page,
}) => {
  await stubPlatform(page);
  await page.goto("/transelec/calidad");
  await expect(page.getByTestId("quality-panel")).toBeVisible();
  await expect(page.getByTestId("web-edit-conflicts")).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// The header pill and its log (indicator spec §4-§5)
// ---------------------------------------------------------------------------

function logEntry(overrides: Record<string, unknown> = {}) {
  return {
    ...BASE_OVERRIDE,
    id: 31,
    state: "aplicada",
    ended_at: null,
    ended_by_display_name: null,
    ...overrides,
  };
}

const ONE_IN_FORCE = {
  in_force_count: 1,
  needs_review_count: 0,
  entries: [
    logEntry(),
    logEntry({
      id: 30,
      state: "discarded",
      source_row_number: null,
      web_value: "Tachado",
      ended_at: "2026-10-04T16:00:00+00:00",
      ended_by_display_name: "Dev Admin",
    }),
  ],
};

/** The in-memory edits as the history route would list them, newest first. */
function withHistory(edits: Override[]): StubOptions {
  const base = statefulEdits(edits);
  return {
    ...base,
    extra: async (page: Page) => {
      await base.extra?.(page);
      await page.route("**/api/transelec/overrides/history*", (route) =>
        fulfill(route, {
          in_force_count: edits.length,
          needs_review_count: 0,
          entries: [...edits].reverse().map((entry) => logEntry(entry)),
        }),
      );
    },
  };
}

test("the pill opens the log; Esc and an outside click close it, and focus returns to the pill", async ({
  page,
}) => {
  await stubPlatform(page, { history: ONE_IN_FORCE });
  await page.goto("/transelec");
  await expect(page.getByTestId("kpi-row")).toBeVisible();

  const pill = page.getByRole("button", { name: "1 edición web" });
  await expect(pill).toHaveAttribute("aria-expanded", "false");
  await pill.click();
  const log = page.getByRole("dialog", { name: "Ediciones web" });
  await expect(log).toBeVisible();
  await expect(log.getByRole("heading", { name: "Ediciones web" })).toBeFocused();
  await expect(pill).toHaveAttribute("aria-expanded", "true");
  await expect(log.getByTestId("edit-log-30")).toContainText(
    "revertida al valor de la planilla · Dev Admin",
  );

  await page.keyboard.press("Escape");
  await expect(log).toBeHidden();
  await expect(pill).toBeFocused();
  await expect(pill).toHaveAttribute("aria-expanded", "false");

  await pill.click();
  await expect(log).toBeVisible();
  await page.mouse.click(5, 600);
  await expect(log).toBeHidden();
});

test("a log entry opens the Explorador drawer on its row, and an edit there updates the log", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await stubPlatform(page, withHistory([{ ...BASE_OVERRIDE, id: 31 }]));
  await page.goto("/transelec");
  await page.getByRole("button", { name: "1 edición web" }).click();
  await page.getByTestId("edit-log-31").getByRole("link").click();

  await expect(page).toHaveURL(/\/transelec\/explorador\?q=PMF-001&fila=1$/);
  await expect(page.getByRole("dialog", { name: "Ediciones web" })).toBeHidden();
  const drawer = page.getByTestId("row-drawer");
  await expect(drawer.getByTestId("drawer-provenance")).toContainText("Fila de origen 1");

  // The stub's version has a column for «Estado resumido» only. A second
  // edit of the same cell replaces the first, as the server does.
  await drawer.getByRole("button", { name: "Editar Estado resumido" }).click();
  await drawer.getByLabel("Nuevo valor de Estado resumido").fill("Desistido");
  await drawer.getByRole("button", { name: "Guardar" }).click();
  await expect(drawer.getByTestId("editables-status")).toContainText(
    "Se guardó el cambio en Estado resumido.",
  );

  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(page).toHaveURL(/\/transelec\/explorador\?q=PMF-001$/);
  const pill = page.getByRole("button", { name: "1 edición web" });
  await pill.click();
  const log = page.getByRole("dialog", { name: "Ediciones web" });
  await expect(log.getByRole("listitem")).toHaveCount(1);
  await expect(log.getByRole("listitem").first()).toContainText("Desistido");
  expect(consoleErrors).toEqual([]);
});

test("a log entry whose row is gone says so instead of opening a drawer", async ({
  page,
}) => {
  await stubPlatform(page, {
    history: {
      in_force_count: 1,
      needs_review_count: 0,
      entries: [logEntry({ source_row_number: 999 })],
    },
  });
  await page.goto("/transelec");
  await page.getByRole("button", { name: "1 edición web" }).click();
  await page.getByTestId("edit-log-31").getByRole("link").click();

  await expect(
    page.getByText("No se encontró esta fila en la versión activa."),
  ).toBeVisible();
  await expect(page.getByTestId("row-drawer")).toHaveCount(0);
  await expect(page).toHaveURL(/\/transelec\/explorador\?q=PMF-001$/);
});

test("a viewer sees the pill and the log, without the operators' footer", async ({
  page,
}) => {
  await stubPlatform(page, { me: VIEWER, history: ONE_IN_FORCE });
  await page.goto("/transelec");
  await page.getByRole("button", { name: "1 edición web" }).click();
  const log = page.getByRole("dialog", { name: "Ediciones web" });
  await expect(log).toBeVisible();
  await expect(log.getByTestId("edit-log-31")).toBeVisible();
  await expect(log.getByRole("link", { name: /Ediciones web/ })).toHaveCount(0);
  await expect(log.getByRole("button", { name: /Descargar/ })).toHaveCount(0);
});

test("the log's arrow sits on the line of the values it joins", async ({ page }) => {
  await stubPlatform(page, { history: ONE_IN_FORCE });
  await page.goto("/transelec");
  await page.getByRole("button", { name: "1 edición web" }).click();
  const change = page.getByTestId("edit-log-31").locator(".edit-log-change");
  const before = await change.locator(".edit-log-value").first().boundingBox();
  const arrow = await change.locator('[aria-hidden="true"]').boundingBox();
  if (!before || !arrow) throw new Error("log entry not measured");
  const middle = (box: { y: number; height: number }) => box.y + box.height / 2;
  expect(Math.abs(middle(arrow) - middle(before))).toBeLessThanOrEqual(3);
});
