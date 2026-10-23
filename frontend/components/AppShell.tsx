"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import type { Health, Reminder } from "@/lib/types";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/upload", label: "Add" },
  { href: "/items", label: "Inventory" },
  { href: "/timeline", label: "Timeline" },
  { href: "/reminders", label: "Reminders" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [due, setDue] = useState<Reminder[]>([]);

  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      try {
        const [nextHealth, reminders] = await Promise.all([
          api<Health>("/health"),
          api<{ reminders: Reminder[] }>("/reminders"),
        ]);
        if (stopped) return;
        setHealth(nextHealth);
        setOffline(false);
        const ready = reminders.reminders.filter(
          (reminder) => reminder.status === "scheduled" && new Date(reminder.remind_at).getTime() <= Date.now(),
        );
        setDue(ready);
      } catch {
        if (!stopped) setOffline(true);
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), 20000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  async function dismiss(reminder: Reminder) {
    setDue((current) => current.filter((item) => item.id !== reminder.id));
    try {
      await api(`/reminders/${reminder.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "seen" }),
      });
    } catch {
      setDue((current) => [reminder, ...current]);
    }
  }

  const warnings: string[] = [];
  if (offline) warnings.push("The local API isn't running. Start the backend on port 8000.");
  else if (health && !health.ollama.available) {
    warnings.push("Ollama isn't reachable. You can still enter items by hand.");
  } else if (health && !health.ollama.model_present) {
    warnings.push(`Ollama is up, but ${health.ollama.model} is not installed.`);
  }
  if (health && !health.tesseract.available) {
    warnings.push("Tesseract isn't installed, so photos can't be read yet. Text PDFs and manual entry still work.");
  }

  return (
    <div className="min-h-screen md:pl-64">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col bg-navy-900 text-paper md:flex">
        <div className="border-b border-white/10 px-6 py-7">
          <p className="text-[11px] uppercase tracking-[0.22em] text-gold">On this computer</p>
          <Link href="/" className="mt-2 block font-display text-3xl">
            Don'tLose
          </Link>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3 py-4">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`rounded-xl px-3 py-2.5 text-sm ${
                isActive(pathname, link.href) ? "bg-white/10 text-white" : "text-paper/70 hover:bg-white/5 hover:text-white"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <p className="px-6 pb-6 text-xs leading-5 text-paper/50">
          Receipts stay here. Deadlines are calculated, not guessed.
        </p>
      </aside>

      <header className="sticky top-0 z-20 border-b border-line bg-paper/90 backdrop-blur md:hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <Link href="/" className="font-display text-2xl text-navy-900">
            Don'tLose
          </Link>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`shrink-0 rounded-full px-3 py-1.5 text-sm ${
                isActive(pathname, link.href) ? "bg-navy-900 text-paper" : "bg-white text-ink"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </header>

      <div className="mx-auto max-w-6xl px-4 py-6 md:px-8 md:py-10">
        {warnings.map((warning) => (
          <p key={warning} className="mb-3 rounded-2xl border border-gold/30 bg-gold/10 px-4 py-3 text-sm text-navy-900" role="status">
            {warning}
          </p>
        ))}
        {due.slice(0, 3).map((reminder) => (
          <div key={reminder.id} className="mb-3 flex items-start justify-between gap-4 rounded-2xl bg-navy-900 px-4 py-3 text-paper">
            <div>
              <p className="text-[11px] uppercase tracking-[0.16em] text-gold">Reminder</p>
              <p className="mt-1 text-sm">{reminder.message}</p>
            </div>
            <button className="text-sm text-paper/80 underline" type="button" onClick={() => void dismiss(reminder)}>
              Dismiss
            </button>
          </div>
        ))}
        {children}
      </div>
    </div>
  );
}
