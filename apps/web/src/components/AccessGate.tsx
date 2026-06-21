"use client";

import { useState } from "react";

export function AccessGate({
  onSubmit,
  error,
}: {
  onSubmit: (token: string) => void;
  error?: string | null;
}) {
  const [token, setToken] = useState("");
  return (
    <div className="flex h-screen items-center justify-center bg-slate-50">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (token.trim()) onSubmit(token.trim());
        }}
        className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <div className="mb-4 flex items-center gap-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-indigo-600 text-sm font-bold text-white">
            C
          </span>
          <div>
            <h1 className="text-sm font-semibold leading-tight text-slate-800">CaseLens</h1>
            <p className="text-xs leading-tight text-slate-400">Demo protegido</p>
          </div>
        </div>
        <label htmlFor="access-token" className="block text-sm font-medium text-slate-700">
          Token de acceso
        </label>
        <input
          id="access-token"
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          autoFocus
          placeholder="Pega el token del demo"
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"
        />
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={!token.trim()}
          className="mt-4 w-full rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400"
        >
          Entrar
        </button>
        <p className="mt-3 text-xs text-slate-400">
          Compuerta del demo, no es autenticación real.
        </p>
      </form>
    </div>
  );
}
