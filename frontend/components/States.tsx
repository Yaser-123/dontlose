import type { ReactNode } from "react";

export function Loading({ label }: { label: string }) {
  return (
    <div className="card p-8" role="status">
      <p className="font-display text-2xl text-navy-900">{label}</p>
      <div className="indeterminate mt-5 h-1.5 rounded-full" />
    </div>
  );
}

export function Empty({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="card px-8 py-12 text-center">
      <p className="font-display text-3xl text-navy-900">{title}</p>
      <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-mist">{body}</p>
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-2xl border border-clay/30 bg-clay/5 px-5 py-4 text-sm text-clay" role="alert">
      <p>{message}</p>
      {onRetry ? (
        <button className="btn-ghost mt-3 !py-1.5" onClick={onRetry} type="button">
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function SuccessNote({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-pine/20 bg-pine/5 px-5 py-4 text-sm text-pine" role="status">
      {message}
    </div>
  );
}
