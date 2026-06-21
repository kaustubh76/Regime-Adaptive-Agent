// Small presentation helpers shared across the cards.

export function fmtUsd(n: number | null | undefined, dp = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
}

export function fmtPct(frac: number | null | undefined, dp = 1): string {
  if (frac === null || frac === undefined || Number.isNaN(frac)) return "—";
  return `${(frac * 100).toFixed(dp)}%`;
}

/** Absolute percentage from a 0..1 fraction, rounded to `dp` decimals (no sign forced).
 * Use for budgets/dominance/health; use fmtSignedPct for deltas. */
export function fmtPctRounded(frac: number | null | undefined, dp = 0): string {
  if (frac === null || frac === undefined || Number.isNaN(frac)) return "—";
  return `${(frac * 100).toFixed(dp)}%`;
}

export function fmtSignedPct(frac: number | null | undefined, dp = 2): string {
  if (frac === null || frac === undefined || Number.isNaN(frac)) return "—";
  const s = (frac * 100).toFixed(dp);
  return `${frac >= 0 ? "+" : ""}${s}%`;
}

/** Friendly label for a rebalance's candle data-source. CMC-only by design: any non-CMC /
 * legacy / null provenance returns null so the UI renders NO source label (it never surfaces
 * an exchange name — the agent now decides 100% on CoinMarketCap data). */
export function candleSourceLabel(s: string | null | undefined): string | null {
  if (s === "cmc_4h") return "CMC 4h candles";
  if (s === "cmc_daily") return "CMC daily candles";
  return null;
}

/** Sanitize a CMC-provided display label (a trending narrative / category name) so the UI never
 * renders the exchange word. CMC names some ecosystem categories after the "Binance" exchange; we
 * show the chain context instead ("Avalanche"). Display-only — never alters the data. */
export function cmcLabel(s: string): string {
  return s.replace(/binance/gi, "Avalanche");
}

/** Human network label. The functional id stays "avax-testnet"/"avalanche-fuji"/etc (SDK preset +
 * explorer-subdomain logic); this is DISPLAY only — the proper modern name. */
export function networkLabel(n: string | null | undefined): string {
  switch ((n ?? "").toLowerCase()) {
    case "avax-testnet":
    case "avalanche-fuji":
      return "Avalanche Fuji";
    case "avax":
    case "avax-mainnet":
    case "avalanche":
      return "Avalanche C-Chain";
    default:
      return n || "—";
  }
}

/** Block-explorer base URL for on-chain links. Avalanche (Snowtrace) for every network; a
 * "*-testnet"/"*-fuji" network → testnet subdomain. DISPLAY only — the network id is unchanged. */
export function getExplorerBase(network: string | null | undefined): string {
  const n = (network ?? "").toLowerCase();
  const isTestnet = n.includes("testnet") || n.includes("fuji") || n.includes("sepolia");
  return `https://${isTestnet ? "testnet." : ""}snowtrace.io`;
}

export function shortAddr(a: string | null | undefined): string {
  if (!a || a.length < 10) return a || "—";
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}

export function shortHash(h: string): string {
  if (!h || h.length < 10) return h;
  return `${h.slice(0, 8)}…${h.slice(-6)}`;
}

/** Resolve an ERC-8183 deliverable URL to something a browser can open. The provider pins the
 * deliverable on IPFS, so the journal/SDK hands back an `ipfs://CID[/path]` URI — rewrite it to a
 * public gateway so the link is clickable. `http(s)://` URLs pass through unchanged; falsy → "". */
export function ipfsUrl(u: string | null | undefined): string {
  if (!u) return "";
  const m = /^ipfs:\/\/(.+)$/i.exec(u.trim());
  return m ? `https://ipfs.io/ipfs/${m[1].replace(/^ipfs\//i, "")}` : u;
}

export function clockHM(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ageLabel(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "no signal";
  if (seconds < 90) return `${Math.round(seconds)}s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 129600) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

// Stable per-token colour for the weights donut / legends.
const TOKEN_COLORS: Record<string, string> = {
  USDT: "#3b82f6",
  BNB: "#f0b90b",
  ETH: "#8b9dff",
  CAKE: "#23c4d6",
  LINK: "#2a5ada",
  UNI: "#ff2d78",
  AVAX: "#e84142",
  DOT: "#e6007a",
  DOGE: "#c2a633",
};

export function tokenColor(sym: string): string {
  return TOKEN_COLORS[sym] ?? "#94a3b8";
}

// Colour ramp for the Fear & Greed value (0 = fear/red → 100 = greed/green).
// Aligned to the signature tokens: down red → brand gold → up green.
export function fgColor(fg: number | null | undefined): string {
  if (fg === null || fg === undefined) return "#8a8f9c";
  if (fg <= 24) return "#ea3943";
  if (fg <= 44) return "#f0b90b";
  if (fg <= 55) return "#d4a017";
  if (fg <= 74) return "#5bbf6a";
  return "#16c784";
}

// Regime score 0..1 → risk-off red to risk-on green (token-aligned).
export function regimeColor(s: number | null | undefined): string {
  if (s === null || s === undefined) return "#8a8f9c";
  if (s < 0.2) return "#ea3943";
  if (s < 0.5) return "#f0b90b";
  if (s < 0.75) return "#3861fb";
  return "#16c784";
}
