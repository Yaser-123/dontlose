"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";

import { Empty, ErrorNote, Loading, SuccessNote } from "@/components/States";
import { api } from "@/lib/api";
import { formatWhen, localInputToIso, remindBefore, toLocalInput } from "@/lib/format";
import type { Health, ItemSummary, Reminder } from "@/lib/types";

export default function RemindersPage() {
  return (
    <Suspense fallback={<Loading label="Opening reminders" />}>
      <Reminders />
    </Suspense>
  );
}

function Reminders() {
  const params = useSearchParams();
  const [reminders, setReminders] = useState<Reminder[] | null>(null);
  const [items, setItems] = useState<ItemSummary[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [windowsNotifications, setWindowsNotifications] = useState<boolean | null>(null);
  const [form, setForm] = useState({
    item_id: params.get("item") || "",
    deadline_id: params.get("deadline") || "",
    remind_at: toLocalInput(new Date(Date.now() + 60 * 60 * 1000)),
    message: "Check this deadline.",
  });

  function load() {
    Promise.all([api<{ reminders: Reminder[] }>("/reminders"), api<{ items: ItemSummary[] }>("/items?status=active")])
      .then(([reminderData, itemData]) => {
        setReminders(reminderData.reminders);
        setItems(itemData.items);
        setError("");
        const item = itemData.items.find((entry) => entry.id === (params.get("item") || form.item_id));
        const deadline = item?.next_deadline;
        if (params.get("deadline") && deadline) {
          setForm((current) => ({
            ...current,
            remind_at: remindBefore(deadline.due_date),
            message: `${deadline.label} for ${item?.title}`,
          }));
        }
      })
      .catch((reason: Error) => setError(reason.message));
  }

  useEffect(() => {
    load();
    api<Health>("/health")
      .then((health) => setWindowsNotifications(health.windows_notifications))
      .catch(() => setWindowsNotifications(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    try {
      await api("/reminders", {
        method: "POST",
        body: JSON.stringify({
          item_id: form.item_id || null,
          deadline_id: form.deadline_id || null,
          remind_at: localInputToIso(form.remind_at),
          message: form.message,
        }),
      });
      setSuccess("Reminder saved. Windows shows it at that time, even if this tab is closed.");
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save that reminder.");
    }
  }

  async function setStatus(reminder: Reminder, status: "seen" | "dismissed" | "scheduled") {
    try {
      await api(`/reminders/${reminder.id}`, { method: "PATCH", body: JSON.stringify({ status }) });
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update that reminder.");
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-[11px] uppercase tracking-[0.18em] text-gold">Reminders</p>
        <h1 className="mt-2 font-display text-4xl text-navy-900 md:text-5xl">A nudge on this computer</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-mist">
          Windows shows the reminder at the time you pick, even if this tab is closed. Don'tLose has to be running on
          this computer. Opening the site later still shows the same reminder until you dismiss it.
        </p>
      </header>
      {windowsNotifications === false ? (
        <p className="rounded-2xl border border-gold/30 bg-gold/10 px-4 py-3 text-sm text-navy-900" role="status">
          Windows notifications are turned off, so a popup cannot appear yet. Turn them on in Settings, then System,
          then Notifications. The reminder still shows as a banner here when you open Don'tLose.
        </p>
      ) : null}
      {error ? <ErrorNote message={error} /> : null}
      {success ? <SuccessNote message={success} /> : null}
      <form className="card grid gap-4 p-5 md:grid-cols-2" onSubmit={(event) => void save(event)}>
        <label>
          <span className="label">Item</span>
          <select
            className="input"
            value={form.item_id}
            onChange={(event) => {
              const item = items.find((entry) => entry.id === event.target.value);
              setForm({
                ...form,
                item_id: event.target.value,
                deadline_id: item?.next_deadline?.id || "",
                message: item?.next_deadline ? `${item.next_deadline.label} for ${item.title}` : form.message,
                remind_at: item?.next_deadline ? remindBefore(item.next_deadline.due_date) : form.remind_at,
              });
            }}
          >
            <option value="">No item</option>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label">When</span>
          <input className="input" type="datetime-local" required value={form.remind_at} onChange={(event) => setForm({ ...form, remind_at: event.target.value })} />
        </label>
        <label className="md:col-span-2">
          <span className="label">Message</span>
          <input className="input" required maxLength={240} value={form.message} onChange={(event) => setForm({ ...form, message: event.target.value })} />
        </label>
        <div>
          <button className="btn-primary" type="submit">
            Save reminder
          </button>
        </div>
      </form>
      {reminders === null && !error ? <Loading label="Loading reminders" /> : null}
      {reminders && reminders.length === 0 ? (
        <Empty title="No reminders yet" body="Pick an item and a time. Windows notifies you then, and the banner stays here until you dismiss it." />
      ) : null}
      <div className="space-y-3">
        {reminders?.map((reminder) => (
          <article key={reminder.id} className="card flex flex-wrap items-center justify-between gap-3 p-4">
            <div>
              <p className="font-medium">{reminder.message}</p>
              <p className="text-sm text-mist">
                {formatWhen(reminder.remind_at)} · {reminder.status}
                {reminder.item_title ? ` · ${reminder.item_title}` : ""}
              </p>
            </div>
            <div className="flex gap-2">
              {reminder.item_id ? (
                <Link className="btn-ghost !py-1.5" href={`/items/${reminder.item_id}`}>
                  Open
                </Link>
              ) : null}
              {reminder.status === "scheduled" ? (
                <button className="btn-ghost !py-1.5" type="button" onClick={() => void setStatus(reminder, "dismissed")}>
                  Dismiss
                </button>
              ) : (
                <button className="btn-ghost !py-1.5" type="button" onClick={() => void setStatus(reminder, "scheduled")}>
                  Restore
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
