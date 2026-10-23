"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Empty, ErrorNote, Loading } from "@/components/States";
import { api } from "@/lib/api";
import { daysLabel, formatDate } from "@/lib/format";
import { CATEGORIES, type ItemStatus, type ItemSummary } from "@/lib/types";

export default function InventoryPage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("active");
  const [items, setItems] = useState<ItemSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const handle = window.setTimeout(() => {
      const params = new URLSearchParams();
      if (query.trim()) params.set("q", query.trim());
      if (category) params.set("category", category);
      if (status) params.set("status", status);
      api<{ items: ItemSummary[] }>(`/items?${params.toString()}`)
        .then((data) => {
          setItems(data.items);
          setError("");
        })
        .catch((reason: Error) => setError(reason.message));
    }, 200);
    return () => window.clearTimeout(handle);
  }, [query, category, status]);

  return (
    <div className="space-y-6">
      <header>
        <p className="text-[11px] uppercase tracking-[0.18em] text-gold">Inventory</p>
        <h1 className="mt-2 font-display text-4xl text-navy-900 md:text-5xl">Everything you're tracking</h1>
      </header>
      <div className="grid gap-3 md:grid-cols-3">
        <label className="md:col-span-1">
          <span className="label">Search</span>
          <input className="input" placeholder="Name, merchant, or a saved value" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label>
          <span className="label">Category</span>
          <select className="input" value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="">All</option>
            {CATEGORIES.map((entry) => (
              <option key={entry.value} value={entry.value}>
                {entry.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label">Status</span>
          <select className="input" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">Any</option>
            {(["active", "resolved", "archived"] as ItemStatus[]).map((entry) => (
              <option key={entry} value={entry}>
                {entry}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error ? <ErrorNote message={error} /> : null}
      {items === null && !error ? <Loading label="Searching your items" /> : null}
      {items && items.length === 0 ? (
        <Empty
          title={query || category ? "Nothing matches" : "No items in this view"}
          body="Try another search, or add a receipt."
          action={
            <Link className="btn-primary" href="/upload">
              Add an item
            </Link>
          }
        />
      ) : null}
      <div className="grid gap-3">
        {items?.map((item) => (
          <Link key={item.id} href={`/items/${item.id}`} className="card flex flex-wrap items-center justify-between gap-4 p-5">
            <div>
              <p className="text-[11px] uppercase tracking-[0.16em] text-mist">
                {CATEGORIES.find((entry) => entry.value === item.category)?.label}
                {item.needs_review ? " · Review" : ""}
              </p>
              <h2 className="mt-1 font-display text-3xl text-navy-900">{item.title}</h2>
              <p className="mt-1 text-sm text-mist">
                {[item.merchant, item.price_display, item.purchase_date ? formatDate(item.purchase_date) : ""]
                  .filter(Boolean)
                  .join(" · ") || "No details yet"}
              </p>
            </div>
            {item.next_deadline ? (
              <p className="text-sm text-navy-900">
                {item.next_deadline.label}
                <span className="mt-1 block text-mist">{daysLabel(item.next_deadline.days_remaining)}</span>
              </p>
            ) : (
              <p className="text-sm text-mist">No open deadline</p>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
