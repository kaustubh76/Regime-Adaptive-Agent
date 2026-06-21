import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";

interface SparklineProps {
  data: number[];
  color?: string;
  height?: number;
  className?: string;
}

/** Minimal inline trend line (no axes / dots) — used in the hero NAV stat. */
export default function Sparkline({ data, color = "#16c784", height = 28, className = "" }: SparklineProps) {
  if (data.length < 2) return null;
  const rows = data.map((v, i) => ({ i, v }));
  const lo = Math.min(...data);
  const hi = Math.max(...data);
  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
          <YAxis domain={[lo, hi]} hide />
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false} isAnimationActive animationDuration={400} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
