"use client";

import { useEffect, useState } from "react";

import { DeadlineCard } from "@/components/DeadlineCard";
import { Empty, ErrorNote, Loading } from "@/components/States";
import { api } from "@/lib/api";
import { monthLabel } from "@/lib/format";
import type { Deadline } from "@/lib/types";

export default function TimelinePage() {
  const [status, setStatus] = useState<"open" | "done" | "dismissed">("open");
  const [deadlines, setDeadlines] = useState<Deadline[] | null>(null);
  const [error, setError] = useState("");

  function load(next = status) {
    setError("");
    api<{ deadlines: Deadline[] }>(`/deadlines?status=${next}`)
      .then((data) => setDeadlines(data.deadlines))
      .catch((reason: Error) => setError(reason.message));
  }

  useEffect(() => {
    load(status);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function update(deadline: Deadline, next: "done" | "dismissed") {
    try {
      await api(`/deadlines/${deadline.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status: next }),
      });
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update that deadline.");
    }
  }

  const groups = new Map<string, Deadline[]>();
  for (const deadline of deadlines || []) {
    const key = deadline.due_date.slice(0, 7);
    groups.set(key, [...(groups.get(key) || []), deadline]);
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-gold">Timeline</p>
          <h1 className="mt-2 font-display text-4xl text-navy-900 md:text-5xl">What comes due, in order</h1>
        </div>
        <div className="flex gap-2">
          {(["open", "done", "dismissed"] as const).map((choice) => (
            <button key={choice} className={status === choice ? "btn-primary" : "btn-ghost"} type="button" onClick={() => setStatus(choice)}>
              {choice}
            </button>
          ))}
        </div>
      </header>
      {error ? <ErrorNote message={error} onRetry={() => load()} /> : null}
      {deadlines === null && !error ? <Loading label="Lining up the dates" /> : null}
      {deadlines && deadlines.length === 0 ? (
        <Empty title="The timeline is clear" body="Deadlines appear here only after a date can be calculated from verified facts." />
      ) : null}
      {[...groups.entries()].map(([month, rows]) => (
        <section key={month} className="space-y-3">
          <h2 className="font-display text-2xl text-navy-900">{monthLabel(`${month}-01`)}</h2>
          <div className="space-y-3 border-l border-line pl-4">
            {rows.map((deadline) => (
              <DeadlineCard
                key={deadline.id}
                deadline={deadline}
                onDone={status === "open" ? (item) => void update(item, "done") : undefined}
                onDismiss={status === "open" ? (item) => void update(item, "dismissed") : undefined}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
