// 백엔드(FastAPI) 호출 클라이언트 + 타입(스키마 계약)

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Publication = {
  channel: string;
  status: "listed" | "rejected" | "pending";
  channel_product_no: string | null;
};

export type Listing = {
  id: string;
  title: string;
  status: "ready" | "published" | "paused" | "review" | "blocked" | "margin_rejected";
  note: string;
  price_krw: number | null;
  market_score: number | null;
  recommendation: string | null;
  channel_product_no: string | null;
  publications: Publication[];
};

export type Order = {
  id: string;
  product_id: string;
  quantity: number;
  buyer: string;
  status: "pending_approval" | "awaiting_purchase" | "purchased" | "rejected";
  guard_action: "auto_order" | "approval_required";
  guard_reason: string;
  profit_krw: number | null;
  fulfillment_id: string | null;
  amazon_order_no: string | null;
  tracking_no: string | null;
};

export type Stats = {
  listings_total: number;
  by_status: Record<string, number>;
  orders_pending: number;
};

export type SweepChange = {
  id: string;
  action: "pause" | "reprice" | "resume";
  reason: string;
  new_price_krw: number | null;
};

export type SweepResult = { changed: number; changes: SweepChange[] };

export type Config = {
  modes: Record<string, "real" | "mock">;
  fx_rate: string;
  channels: string[];
  sourcing_category: string;
};

async function req<T>(path: string, method: "GET" | "POST" = "GET"): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method, cache: "no-store" });
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `POST ${path} → ${res.status}`);
  }
  return res.json();
}

export const api = {
  config: () => req<Config>("/api/config"),
  stats: () => req<Stats>("/api/stats"),
  listings: () => req<Listing[]>("/api/listings"),
  orders: () => req<Order[]>("/api/orders"),
  runSourcing: () => req<Listing[]>("/api/sourcing/run", "POST"),
  runMonitor: () => req<SweepResult>("/api/monitor/run", "POST"),
  approveListing: (id: string) => req<Listing>(`/api/listings/${id}/approve`, "POST"),
  approveOrder: (id: string) => req<Order>(`/api/orders/${id}/approve`, "POST"),
  confirmOrder: (id: string, amazon_order_no: string, tracking_no: string | null) =>
    post<Order>(`/api/orders/${id}/confirm`, { amazon_order_no, tracking_no }),
  rejectOrder: (id: string) => req<Order>(`/api/orders/${id}/reject`, "POST"),
};
