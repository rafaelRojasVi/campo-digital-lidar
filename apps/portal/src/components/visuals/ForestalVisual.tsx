/**
 * Abstract parcel / satellite-polygon motif for the Forestry module. Not a
 * real cadastral map — a restrained geometric identity mark.
 */
export function ForestalVisual() {
  return (
    <svg
      viewBox="0 0 320 200"
      role="img"
      aria-label="Identidad visual de Gestión Predial Forestal: polígonos sobre mapa"
      className="product-visual"
    >
      <g stroke="var(--cd-forestal)" strokeOpacity="0.18" strokeWidth="1">
        {Array.from({ length: 7 }, (_, index) => (
          <line key={`v${index}`} x1={index * 46 + 10} y1={0} x2={index * 46 + 10} y2={200} />
        ))}
        {Array.from({ length: 5 }, (_, index) => (
          <line key={`h${index}`} x1={0} y1={index * 44 + 10} x2={320} y2={index * 44 + 10} />
        ))}
      </g>
      <polygon
        points="40,150 92,120 150,132 170,176 96,186"
        fill="var(--cd-forestal)"
        fillOpacity="0.16"
        stroke="var(--cd-forestal)"
        strokeWidth="1.5"
      />
      <polygon
        points="150,132 208,100 262,118 246,168 170,176"
        fill="var(--cd-forestal)"
        fillOpacity="0.28"
        stroke="var(--cd-forestal)"
        strokeWidth="1.5"
      />
      <polygon
        points="208,100 236,54 288,66 262,118"
        fill="var(--cd-forestal)"
        fillOpacity="0.1"
        stroke="var(--cd-forestal)"
        strokeWidth="1.5"
      />
    </svg>
  )
}
