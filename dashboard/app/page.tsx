"use client";

import { useEffect, useState } from "react";
import {
  api,
  getToken,
  logout,
  UnauthorizedError,
  type Config,
  type Listing,
  type Order,
  type Publication,
  type Stats,
} from "@/lib/api";
import Login from "./Login";

const MODE_LABEL: Record<string, string> = {
  aliexpress: "AliExpress",
  amazon: "Amazon",
  naver: "네이버",
  coupang: "쿠팡",
  gemini: "AI(Gemini)",
  deepl: "번역",
};

const CHANNEL_LABEL: Record<string, string> = { naver: "네이버", coupang: "쿠팡" };

const PUB_BADGE: Record<Publication["status"], string> = {
  listed: "bg-emerald-100 text-emerald-700",
  rejected: "bg-rose-100 text-rose-700",
  pending: "bg-amber-100 text-amber-700",
};

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

const ORDER_LABEL: Record<Order["status"], string> = {
  pending_approval: "승인 대기",
  awaiting_purchase: "매입 대기",
  purchased: "매입 완료",
  rejected: "반려됨",
};

const ORDER_BADGE: Record<Order["status"], string> = {
  pending_approval: "bg-amber-100 text-amber-800",
  awaiting_purchase: "bg-sky-100 text-sky-800",
  purchased: "bg-emerald-100 text-emerald-800",
  rejected: "bg-zinc-200 text-zinc-600",
};

const won = (n: number | null) => (n == null ? "—" : `${n.toLocaleString()}원`);

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [config, setConfig] = useState<Config | null>(null);
  const [listings, setListings] = useState<Listing[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sweepMsg, setSweepMsg] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<Order | null>(null);
  const [needLogin, setNeedLogin] = useState(false);

  async function load() {
    try {
      setErr(null);
      const c = await api.config(); // 공개: 인증 활성 여부 확인
      setConfig(c);
      if (c.auth_enabled && !getToken()) {
        setNeedLogin(true);
        return;
      }
      const [s, l, o] = await Promise.all([api.stats(), api.listings(), api.orders()]);
      setStats(s);
      setListings(l);
      setOrders(o);
      setNeedLogin(false);
    } catch (e) {
      if (e instanceof UnauthorizedError) {
        setNeedLogin(true);
        return;
      }
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
    } catch (e) {
      if (e instanceof UnauthorizedError) setNeedLogin(true);
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

  if (needLogin && config?.google_client_id) {
    return <Login clientId={config.google_client_id} />;
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900">🐻 직구곰 어드민</h1>
          <p className="text-sm text-zinc-500">
            AliExpress → 네이버 스마트스토어 · 등록/발주 사람 승인
          </p>
          {config && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-zinc-400">연동 모드:</span>
              {Object.entries(config.modes).map(([key, mode]) => (
                <span
                  key={key}
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                    mode === "real"
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-zinc-200 text-zinc-500"
                  }`}
                >
                  {MODE_LABEL[key] ?? key} {mode === "real" ? "real" : "mock"}
                </span>
              ))}
              <span className="ml-1 text-[10px] text-zinc-400">FX {config.fx_rate}</span>
            </div>
          )}
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
          {config?.auth_enabled && (
            <button
              onClick={() => { logout(); window.location.reload(); }}
              className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-500 hover:bg-zinc-50"
            >
              로그아웃
            </button>
          )}
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
                    {l.publications.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {l.publications.map((p) => (
                          <span
                            key={p.channel}
                            title={p.channel_product_no ?? p.status}
                            className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${PUB_BADGE[p.status]}`}
                          >
                            {CHANNEL_LABEL[p.channel] ?? p.channel}
                            {p.status === "listed" ? " ✓" : ""}
                          </span>
                        ))}
                      </div>
                    )}
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
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${ORDER_BADGE[o.status]}`}>
                      {ORDER_LABEL[o.status]}
                    </span>
                    {o.status === "purchased" && (
                      <div className="mt-1 text-xs text-zinc-400">
                        {o.amazon_order_no}
                        {o.tracking_no ? ` · 송장 ${o.tracking_no}` : ""}
                      </div>
                    )}
                  </td>
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
                    ) : o.status === "awaiting_purchase" ? (
                      <button
                        onClick={() => setConfirmTarget(o)}
                        disabled={busy}
                        className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
                      >
                        매입 확정
                      </button>
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
        🐻 직구곰 admin · SQLite 영속 + 주기 점검 스케줄러 · 반자동(HITL) 발주 · 멀티채널 동시등록
      </footer>

      {confirmTarget && (
        <ConfirmPurchaseModal
          order={confirmTarget}
          busy={busy}
          onClose={() => setConfirmTarget(null)}
          onSubmit={async (amazonNo, tracking) => {
            await act(() => api.confirmOrder(confirmTarget.id, amazonNo, tracking));
            setConfirmTarget(null);
          }}
        />
      )}
    </main>
  );
}

function ConfirmPurchaseModal({
  order,
  busy,
  onClose,
  onSubmit,
}: {
  order: Order;
  busy: boolean;
  onClose: () => void;
  onSubmit: (amazonNo: string, tracking: string | null) => Promise<void>;
}) {
  const [amazonNo, setAmazonNo] = useState("");
  const [tracking, setTracking] = useState("");

  return (
    <div
      className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-zinc-900">매입 확정</h3>
        <p className="mt-1 text-sm text-zinc-500">
          {order.id} · {order.product_id} · {order.buyer}
          <br />
          Amazon에서 실제 매입을 마친 뒤 주문번호를 입력하세요.
        </p>
        <label className="mt-4 block text-xs font-medium text-zinc-600">
          Amazon 주문번호 <span className="text-rose-500">*</span>
        </label>
        <input
          autoFocus
          value={amazonNo}
          onChange={(e) => setAmazonNo(e.target.value)}
          placeholder="111-1234567-1234567"
          className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none"
        />
        <label className="mt-3 block text-xs font-medium text-zinc-600">송장번호 (선택)</label>
        <input
          value={tracking}
          onChange={(e) => setTracking(e.target.value)}
          placeholder="1Z999AA10123456784"
          className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none"
        />
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={busy}
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          >
            취소
          </button>
          <button
            onClick={() => onSubmit(amazonNo.trim(), tracking.trim() || null)}
            disabled={busy || amazonNo.trim() === ""}
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            확정
          </button>
        </div>
      </div>
    </div>
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
