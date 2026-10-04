/**
 * Calidad: how many web edits the published planilla now contradicts or no
 * longer has a row for. Hidden when there are none, and when the overrides
 * cannot be read: the other Calidad blocks never wait on or depend on this one.
 */
import { useEffect, useState } from "react";
import { listOverrides } from "../api";
import { formatInteger } from "../format";
import { Link, ROUTES } from "../router";
import { SectionHeader } from "../ui/Primitives";

export function WebEditConflicts({ canEdit }: { canEdit: boolean }) {
  const [counts, setCounts] = useState<{
    conflicts: number;
    orphans: number;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    void listOverrides().then((result) => {
      if (cancelled || !result.ok) return;
      setCounts({
        conflicts: result.data.filter(
          (entry) => entry.status === "en_conflicto",
        ).length,
        orphans: result.data.filter((entry) => entry.status === "huerfana")
          .length,
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!counts || counts.conflicts + counts.orphans === 0) return null;

  return (
    <section
      className="ruled"
      aria-labelledby="web-conflicts-title"
      data-testid="web-edit-conflicts"
    >
      <SectionHeader
        id="web-conflicts-title"
        title="Ediciones web en conflicto"
        meta="La planilla publicada manda: el panel muestra su valor hasta que alguien decida."
      />
      <p className="prose">
        {formatInteger(counts.conflicts)}{" "}
        {counts.conflicts === 1 ? "edición difiere" : "ediciones difieren"} de
        la planilla publicada y {formatInteger(counts.orphans)}{" "}
        {counts.orphans === 1 ? "ya no tiene fila" : "ya no tienen fila"} en
        ella.{" "}
        {canEdit && (
          <Link to={ROUTES.ediciones}>Revisarlas en Datos → Ediciones web</Link>
        )}
      </p>
    </section>
  );
}
