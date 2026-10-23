"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { DeadlineCard } from "@/components/DeadlineCard";
import { Empty, ErrorNote, Loading } from "@/components/States";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Dashboard } from "@/lib/types";
import { CATEGORIES } from "@/lib/types";

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  function load() {
    setError("");
    api<Dashboard>("/dashboard")
      .then(setData)
      .catch((reason: Error) => setError(reason.message));
  }

  useEffect(() => {
    load();
  }, []);

  if (error) return <ErrorNote message={error} onRetry={load} />;
  if (!data) return <Loading label="Gathering your deadlines" />;

  const clear = data.counts.overdue === 0 && data.alerts.length === 0;
  const stats = [
    ["Active items", data.counts.active_items],
    ["Open deadlines", data.counts.open_deadlines],
    ["Need a look", data.counts.needs_review],
    ["Overdue", data.counts.overdue],
  ];

  return (
    <div className="space-y-8">
      <section className="rise">
        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-gold">As of {formatDate(data.today)}</p>
        <h1 className="mt-2 max-w-3xl font-display text-4xl leading-tight text-navy-900 md:text-6xl">
          {clear ? "Nothing is slipping past you." : "A few windows are closing."}
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-mist">
          Don'tLose watches return windows, warranties, renewals, and expiring documents. A date lands on the
          timeline only when the document states it, or you confirm it.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link className="btn-primary" href="/upload">
            Add a document
          </Link>
          <Link className="btn-ghost" href="/timeline">
            Open the timeline
          </Link>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map(([label, value], index) => (
          <div key={label} className="card rise p-5" style={{ animationDelay: `${index * 60}ms` }}>
            <p className="label">{label}</p>
            <p className="font-display text-4xl text-navy-900">{value}</p>
          </div>
        ))}
      </section>

      <section className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-3 lg:col-span-3">
          <h2 className="font-display text-3xl text-navy-900">Priority</h2>
          {data.alerts.length === 0 ? (
            <Empty
              title="No urgent deadlines"
              body="Overdue items and anything due within a week will show up here."
            />
          ) : (
            data.alerts.map((deadline) => <DeadlineCard key={deadline.id} deadline={deadline} />)
          )}
        </div>
        <div className="space-y-3 lg:col-span-2">
          <h2 className="font-display text-3xl text-navy-900">Needs review</h2>
          {data.needs_review.length === 0 ? (
            <Empty title="All caught up" body="Extracted facts you haven't confirmed will wait here." />
          ) : (
            data.needs_review.map((item) => (
              <Link key={item.id} href={`/items/${item.id}`} className="card block p-4 hover:-translate-y-0.5 hover:transition">
                <p className="font-medium text-navy-900">{item.title}</p>
                <p className="mt-1 text-sm text-mist">
                  {item.merchant || CATEGORIES.find((entry) => entry.value === item.category)?.label}
                  {item.next_deadline ? ` · ${item.next_deadline.label}` : ""}
                </p>
              </Link>
            ))
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-display text-3xl text-navy-900">Later</h2>
        {data.upcoming.length === 0 ? (
          <p className="text-sm text-mist">Nothing is scheduled after this week.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {data.upcoming.map((deadline) => (
              <DeadlineCard key={deadline.id} deadline={deadline} />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-end justify-between">
          <h2 className="font-display text-3xl text-navy-900">Recent items</h2>
          <Link href="/items" className="text-sm text-navy-800 underline">
            View inventory
          </Link>
        </div>
        {data.recent_items.length === 0 ? (
          <Empty
            title="Your inventory is empty"
            body="Upload a receipt or type an item you already know. Nothing is invented to fill this space."
            action={
              <Link className="btn-primary" href="/upload">
                Add the first item
              </Link>
            }
          />
        ) : (
          <div className="grid gap-3 md:grid-cols-3">
            {data.recent_items.map((item) => (
              <Link key={item.id} href={`/items/${item.id}`} className="card block p-5">
                <p className="text-[11px] uppercase tracking-[0.16em] text-mist">
                  {CATEGORIES.find((entry) => entry.value === item.category)?.label}
                </p>
                <h3 className="mt-2 font-display text-2xl text-navy-900">{item.title}</h3>
                <p className="mt-2 text-sm text-mist">
                  {item.price_display || item.merchant || "No price yet"}
                  {item.purchase_date ? ` · ${formatDate(item.purchase_date)}` : ""}
                </p>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
