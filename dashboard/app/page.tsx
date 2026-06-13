"use client";

import { useEffect, useState } from "react";
import { api, type Listing, type Order, type Stats } from "@/lib/api";

const LISTING_BADGE: Record<Listing["status"], string> = {
  ready: "bg-amber-100 text-amber-800",
  published: "bg-emerald-100 text-emerald-800",
  paused: "bg-orange-100 text-orange-700",
  review: "bg-sky-100 text-sky-800",
  blocked: "bg-rose-100 text-rose-700",
  margin_rejected: "bg-zinc-200 text-zinc-600",
};

const LISTING_LABEL: Record<Listing["status"], string> = {
  ready: "승인 대기",
  published: "발행됨",
  paused: "일시중지",
  review: "검토 필요",
  blocked: "차단됨",
  margin_rejected: "마진 미달",
};

const won = (n: number | null) => (n == null ? "—" : `${n.toLocaleString()}원`);

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [listings, setListings] = useState<Listing[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sweepMsg, setSweepMsg] = useState<string | null>(null);

  async function load() {
    try {
      setErr(null);
      const [s, l, o] = await Promise.all([api.stats(), api.listings(), api.orders()]);
      setStats(s);
      setListings(l);
      setOrders(o);
    } catch {
      setErr("백엔드(http://localhost:8000)에 연결할 수 없습니다. uvicorn 실행 중인지 확인하세요.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function runMonitor() {
    setBusy(true);
    setSweepMsg(null);
    try {
      const res = await api.runMonitor();
      setSweepMsg(
        res.changed === 0
          ? "가격·재고 점검 완료 — 변동 없음"
          : `가격·재고 점검: ${res.changed}건 반영 (${res.changes
              .map((c) => `${c.id} ${c.action}`)
              .join(", ")})`,
      );
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900">🐻 직구곰 어드민</h1>
          <p className="text-sm text-zinc-500">
            Amazon US → 네이버 스마트스토어 · 등록/발주 사람 승인
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={runMonitor}
            disabled={busy}
            className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
          >
            재고·가격 점검
          </button>
          <button
            onClick={() => act(api.runSourcing)}
            disabled={busy}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
          >
            {busy ? "처리 중…" : "소싱 실행"}
          </button>
        </div>
      </header>

      {sweepMsg && (
        <div className="mt-4 rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
          {sweepMsg}
        </div>
      )}

      {err && (
        <div className="mt-6 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {err}
        </div>
      )}

      <section className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="전체 상품" value={stats?.listings_total ?? 0} />
        <Stat label="승인 대기" value={stats?.by_status.ready ?? 0} accent="amber" />
        <Stat label="발행됨" value={stats?.by_status.published ?? 0} accent="emerald" />
        <Stat label="대기 주문" value={stats?.orders_pending ?? 0} accent="rose" />
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold text-zinc-800">소싱 상품</h2>
        <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
              <tr>
                <th className="px-4 py-3">상품</th>
                <th className="px-4 py-3">상태</th>
                <th className="px-4 py-3 text-right">판매가</th>
                <th className="px-4 py-3 text-center">시장성</th>
                <th className="px-4 py-3">비고</th>
                <th className="px-4 py-3 text-right">액션</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {listings.map((l) => (
                <tr key={l.id} className="hover:bg-zinc-50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-zinc-900">{l.title}</div>
                    <div className="text-xs text-zinc-400">{l.id}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${LISTING_BADGE[l.status]}`}>
                      {LISTING_LABEL[l.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-zinc-700">{won(l.price_krw)}</td>
                  <td className="px-4 py-3 text-center">
                    {l.market_score == null ? (
                      <span className="text-zinc-300">—</span>
                    ) : (
                      <span className="tabular-nums font-medium text-zinc-700">
                        {l.market_score}
                        <span className="ml-1 text-xs text-zinc-400">{l.recommendation}</span>
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-500">{l.note}</td>
                  <td className="px-4 py-3 text-right">
                    {l.status === "ready" ? (
                      <button
                        onClick={() => act(() => api.approveListing(l.id))}
                        disabled={busy}
                        className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                      >
                        승인·발행
                      </button>
                    ) : (
                      <span className="text-xs text-zinc-300">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold text-zinc-800">발주 승인 큐</h2>
        <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
              <tr>
                <th className="px-4 py-3">주문</th>
                <th className="px-4 py-3">발주 가드</th>
                <th className="px-4 py-3 text-right">예상이익</th>
                <th className="px-4 py-3">상태</th>
                <th className="px-4 py-3 text-right">액션</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {orders.map((o) => (
                <tr key={o.id} className="hover:bg-zinc-50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-zinc-900">{o.id}</div>
                    <div className="text-xs text-zinc-400">
                      {o.product_id} · {o.buyer} · {o.quantity}개
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={
                        o.guard_action === "auto_order"
                          ? "text-xs font-medium text-emerald-700"
                          : "text-xs font-medium text-rose-700"
                      }
                    >
                      {o.guard_action === "auto_order" ? "✓ 안전" : "⚠ 확인필요"} · {o.guard_reason}
                    </span>
                  </td>
                  <td
                    className={`px-4 py-3 text-right tabular-nums ${
                      (o.profit_krw ?? 0) < 0 ? "text-rose-600" : "text-zinc-700"
                    }`}
                  >
                    {won(o.profit_krw)}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-500">{o.status}</td>
                  <td className="px-4 py-3 text-right">
                    {o.status === "pending_approval" ? (
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => act(() => api.approveOrder(o.id))}
                          disabled={busy}
                          className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                        >
                          발주 승인
                        </button>
                        <button
                          onClick={() => act(() => api.rejectOrder(o.id))}
                          disabled={busy}
                          className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-100 disabled:opacity-50"
                        >
                          반려
                        </button>
                      </div>
                    ) : (
                      <span className="text-xs text-zinc-300">{o.fulfillment_id ?? "—"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <footer className="mt-10 text-center text-xs text-zinc-400">
        🐻 직구곰 admin · SQLite 영속 + 주기 점검 스케줄러 (발주 자동화는 Phase 3)
      </footer>
    </main>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: "amber" | "emerald" | "rose";
}) {
  const color =
    accent === "amber"
      ? "text-amber-600"
      : accent === "emerald"
        ? "text-emerald-600"
        : accent === "rose"
          ? "text-rose-600"
          : "text-zinc-900";
  return (
    <div className="rounded-xl border border-zinc-200 bg-white px-4 py-3">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold tabular-nums ${color}`}>{value}</div>
    </div>
  );
}
