/**
 * Abstract node/tracking-grid motif for the Transelec module. Not a real
 * network diagram — a restrained geometric identity mark.
 */
export function TranselecVisual() {
  const nodes: Array<[number, number]> = [
    [40, 60], [110, 40], [180, 66], [250, 44], [70, 130], [150, 110],
    [220, 140], [280, 100], [40, 160], [190, 176],
  ]
  const edges: Array<[number, number]> = [
    [0, 1], [1, 2], [2, 3], [0, 4], [1, 5], [2, 5], [3, 6], [3, 7],
    [4, 8], [5, 6], [6, 7], [4, 9], [5, 9],
  ]

  return (
    <svg
      viewBox="0 0 320 200"
      role="img"
      aria-label="Identidad visual de Transelec: red de seguimiento estructurado"
      className="product-visual"
    >
      <g stroke="var(--cd-transelec)" strokeOpacity="0.4" strokeWidth="1">
        {edges.map(([a, b]) => (
          <line
            key={`${a}-${b}`}
            x1={nodes[a][0]}
            y1={nodes[a][1]}
            x2={nodes[b][0]}
            y2={nodes[b][1]}
          />
        ))}
      </g>
      {nodes.map(([x, y], index) => (
        <rect
          key={`${x}-${y}`}
          x={x - 5}
          y={y - 5}
          width={10}
          height={10}
          rx={2}
          fill={index % 4 === 0 ? 'var(--cd-transelec)' : 'var(--cd-surface)'}
          stroke="var(--cd-transelec)"
          strokeWidth="1.5"
        />
      ))}
    </svg>
  )
}
