"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

// Google Identity Services 전역 (스크립트 로드 후 주입됨)
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: { client_id: string; callback: (r: { credential: string }) => void }) => void;
          renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void;
        };
      };
    };
  }
}

const GSI_SRC = "https://accounts.google.com/gsi/client";

export default function Login({ clientId }: { clientId: string }) {
  const btnRef = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const onCredential = async (resp: { credential: string }) => {
      try {
        await api.loginWithGoogle(resp.credential);
        window.location.reload(); // 토큰 저장됨 → 새로고침하면 대시보드 진입
      } catch (e) {
        setErr(e instanceof Error ? e.message : "로그인 실패");
      }
    };
    const init = () => {
      if (!window.google || !btnRef.current) return;
      window.google.accounts.id.initialize({ client_id: clientId, callback: onCredential });
      window.google.accounts.id.renderButton(btnRef.current, {
        theme: "outline", size: "large", text: "signin_with", shape: "pill",
      });
    };
    if (window.google) { init(); return; }
    const s = document.createElement("script");
    s.src = GSI_SRC;
    s.async = true;
    s.defer = true;
    s.onload = init;
    document.body.appendChild(s);
  }, [clientId]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6">
      <div className="w-full max-w-sm rounded-2xl border border-zinc-200 bg-white p-8 text-center shadow-sm">
        <div className="text-4xl">🐻</div>
        <h1 className="mt-3 text-xl font-bold text-zinc-900">직구곰 어드민</h1>
        <p className="mt-1 text-sm text-zinc-500">관리자 Google 계정으로 로그인하세요.</p>
        <div ref={btnRef} className="mt-6 flex justify-center" />
        {err && (
          <p className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{err}</p>
        )}
      </div>
    </main>
  );
}
