"use client";

type Point = { label: string; equity: number; pnl: number };

export function EquityChart({ points }: { points: Point[] }) {
  if (points.length <= 1) {
    return (
      <div className="chart-empty">
        <div className="chart-empty-line" />
        <strong>Awaiting the first realized close</strong>
        <span>The equity curve moves only after a paper position is actually closed.</span>
      </div>
    );
  }

  const width = 760;
  const height = 250;
  const padX = 18;
  const padY = 20;
  const values = points.map((point) => point.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = Math.max(max - min, Math.max(Math.abs(max), 1) * 0.002);
  const lower = min - spread * 0.25;
  const upper = max + spread * 0.25;
  const usableW = width - padX * 2;
  const usableH = height - padY * 2;

  const coords = points.map((point, index) => {
    const x = padX + (index / Math.max(points.length - 1, 1)) * usableW;
    const y = padY + (1 - (point.equity - lower) / (upper - lower)) * usableH;
    return { x, y, point };
  });
  const line = coords.map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const area = `${padX},${height - padY} ${line} ${width - padX},${height - padY}`;
  const last = coords.at(-1)!;

  return (
    <div className="chart-wrap" aria-label="Equity curve">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Paper equity over realized closes">
        <defs>
          <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.18" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1={padX} y1={height - padY} x2={width - padX} y2={height - padY} className="chart-axis" />
        <polygon points={area} fill="url(#equityFill)" className="chart-area" />
        <polyline points={line} fill="none" className="chart-line" />
        <circle cx={last.x} cy={last.y} r="4.5" className="chart-dot" />
      </svg>
      <div className="chart-foot">
        <span>{points[0].label}</span>
        <span>Latest: ${points.at(-1)!.equity.toFixed(4)}</span>
      </div>
    </div>
  );
}
