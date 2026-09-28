/**
 * Abstract point-cloud / cross-section motif for the LiDAR module. Not a
 * screenshot or a real measurement — a restrained geometric identity mark.
 */
export function LidarVisual() {
  const points: Array<[number, number]> = [
    [24, 150], [40, 132], [58, 140], [74, 118], [92, 126], [110, 100],
    [128, 108], [146, 82], [164, 92], [182, 68], [200, 78], [218, 54],
    [236, 64], [254, 44], [272, 52], [290, 34],
    [30, 168], [52, 160], [76, 150], [100, 142], [126, 134], [150, 120],
    [176, 112], [200, 100], [226, 90], [250, 78], [274, 68], [296, 56],
  ]

  return (
    <svg
      viewBox="0 0 320 200"
      role="img"
      aria-label="Identidad visual de Cubicación LiDAR: nube de puntos"
      className="product-visual"
    >
      <polyline
        points="24,150 92,126 164,92 236,64 290,34"
        fill="none"
        stroke="var(--cd-lidar)"
        strokeOpacity="0.35"
        strokeWidth="1"
      />
      <polyline
        points="30,168 126,134 226,90 296,56"
        fill="none"
        stroke="var(--cd-lidar)"
        strokeOpacity="0.25"
        strokeWidth="1"
      />
      {points.map(([x, y], index) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r={index % 3 === 0 ? 2.6 : 1.8} fill="var(--cd-lidar)" />
      ))}
    </svg>
  )
}
