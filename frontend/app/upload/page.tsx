"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { ErrorNote, SuccessNote } from "@/components/States";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { CATEGORIES, STAGE_LABELS, type Category, type DocumentInfo } from "@/lib/types";

const ACCEPT = ".png,.jpg,.jpeg,.webp,.tif,.tiff,.bmp,.pdf,image/*,application/pdf";

export default function UploadPage() {
  const [mode, setMode] = useState<"file" | "manual">("file");
  const [dragging, setDragging] = useState(false);
  const [uploads, setUploads] = useState<DocumentInfo[]>([]);
  const [recent, setRecent] = useState<DocumentInfo[] | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "",
    merchant: "",
    category: "receipt" as Category,
    price: "",
    currency: "USD",
    purchase_date: "",
    delivery_date: "",
    return_days: "",
    warranty_months: "",
    warranty_end: "",
    renewal_date: "",
    expiry_date: "",
    notes: "",
  });

  function loadRecent() {
    api<{ documents: DocumentInfo[] }>("/documents?limit=8")
      .then((data) => setRecent(data.documents))
      .catch(() => setRecent([]));
  }

  useEffect(() => {
    loadRecent();
  }, []);

  useEffect(() => {
    if (!uploads.some((file) => file.processing_status === "queued" || file.processing_status === "processing")) {
      return;
    }
    const timer = window.setInterval(async () => {
      const next = await Promise.all(
        uploads.map(async (file) => {
          if (file.processing_status === "ready" || file.processing_status === "error") return file;
          try {
            return await api<DocumentInfo>(`/documents/${file.id}`);
          } catch {
            return file;
          }
        }),
      );
      setUploads(next);
      if (next.every((file) => file.processing_status === "ready" || file.processing_status === "error")) {
        loadRecent();
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [uploads]);

  async function sendFiles(list: FileList | File[]) {
    const files = Array.from(list);
    if (!files.length) return;
    setError("");
    setSuccess("");
    setBusy(true);
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    try {
      const result = await api<{ documents: DocumentInfo[] }>("/documents", { method: "POST", body });
      setUploads(result.documents);
      setSuccess(files.length === 1 ? "File received. Reading it now." : `${files.length} files received. Reading them now.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function removeFile(id: string) {
    setError("");
    setBusy(true);
    try {
      await api(`/documents/${id}`, { method: "DELETE" });
      setRecent((current) => (current ? current.filter((file) => file.id !== id) : current));
      setUploads((current) => current.filter((file) => file.id !== id));
      setPendingDelete(null);
      setSuccess("File deleted. The item and its saved facts stay.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete that file.");
    } finally {
      setBusy(false);
    }
  }

  async function reprocess(id: string) {
    setError("");
    try {
      const updated = await api<DocumentInfo>(`/documents/${id}/reprocess`, { method: "POST" });
      setUploads((current) => current.map((file) => (file.id === id ? updated : file)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not reprocess that file.");
    }
  }

  async function saveManual(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    const payload: Record<string, string> = { title: form.title.trim(), category: form.category };
    for (const [key, value] of Object.entries(form)) {
      if (key === "title" || key === "category") continue;
      if (key === "currency" && !form.price.trim()) continue;
      if (value.trim()) payload[key] = value.trim();
    }
    try {
      const created = await api<{ item: { id: string } }>("/items", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setSuccess("Saved. Deadlines use only the values you entered.");
      window.location.href = `/items/${created.item.id}`;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save that item.");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <header>
        <p className="text-[11px] uppercase tracking-[0.18em] text-gold">Add</p>
        <h1 className="mt-2 font-display text-4xl text-navy-900 md:text-5xl">Bring in a receipt, or type what you know.</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-mist">
          Images and scanned pages are read with Tesseract. Gemma only proposes values, and a value is kept for the
          timeline when it can be found in the text.
        </p>
      </header>

      <div className="flex gap-2">
        {(["file", "manual"] as const).map((choice) => (
          <button
            key={choice}
            type="button"
            className={mode === choice ? "btn-primary" : "btn-ghost"}
            onClick={() => setMode(choice)}
          >
            {choice === "file" ? "Upload files" : "Enter manually"}
          </button>
        ))}
      </div>

      {error ? <ErrorNote message={error} /> : null}
      {success ? <SuccessNote message={success} /> : null}

      {mode === "file" ? (
        <section
          className={`card border-dashed p-8 text-center ${dragging ? "border-navy-700 bg-white" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            void sendFiles(event.dataTransfer.files);
          }}
        >
          <h2 className="font-display text-3xl text-navy-900">Drop images or PDFs</h2>
          <p className="mt-2 text-sm text-mist">Up to 10 files, 20 MB each. PNG, JPG, WEBP, TIFF, BMP, or PDF.</p>
          <label className="btn-primary mt-6 cursor-pointer">
            {busy ? "Uploading…" : "Choose files"}
            <input
              className="sr-only"
              type="file"
              accept={ACCEPT}
              multiple
              disabled={busy}
              onChange={(event) => {
                if (event.target.files) void sendFiles(event.target.files);
                event.target.value = "";
              }}
            />
          </label>
        </section>
      ) : (
        <form className="card grid gap-4 p-6 md:grid-cols-2" onSubmit={(event) => void saveManual(event)}>
          <label className="md:col-span-2">
            <span className="label">Name</span>
            <input className="input" required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
          </label>
          <label>
            <span className="label">Merchant</span>
            <input className="input" value={form.merchant} onChange={(event) => setForm({ ...form, merchant: event.target.value })} />
          </label>
          <label>
            <span className="label">Category</span>
            <select className="input" value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value as Category })}>
              {CATEGORIES.map((category) => (
                <option key={category.value} value={category.value}>
                  {category.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="label">Price</span>
            <input className="input" inputMode="decimal" placeholder="249.00" value={form.price} onChange={(event) => setForm({ ...form, price: event.target.value })} />
          </label>
          <label>
            <span className="label">Currency</span>
            <input className="input" maxLength={3} value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value.toUpperCase() })} />
          </label>
          <label>
            <span className="label">Purchase date</span>
            <input className="input" type="date" value={form.purchase_date} onChange={(event) => setForm({ ...form, purchase_date: event.target.value })} />
          </label>
          <label>
            <span className="label">Delivery date</span>
            <input className="input" type="date" value={form.delivery_date} onChange={(event) => setForm({ ...form, delivery_date: event.target.value })} />
          </label>
          <label>
            <span className="label">Return window (days)</span>
            <input className="input" inputMode="numeric" value={form.return_days} onChange={(event) => setForm({ ...form, return_days: event.target.value })} />
          </label>
          <label>
            <span className="label">Warranty months</span>
            <input className="input" inputMode="numeric" value={form.warranty_months} onChange={(event) => setForm({ ...form, warranty_months: event.target.value })} />
          </label>
          <label>
            <span className="label">Warranty end</span>
            <input className="input" type="date" value={form.warranty_end} onChange={(event) => setForm({ ...form, warranty_end: event.target.value })} />
          </label>
          <label>
            <span className="label">Renewal date</span>
            <input className="input" type="date" value={form.renewal_date} onChange={(event) => setForm({ ...form, renewal_date: event.target.value })} />
          </label>
          <label>
            <span className="label">Expiration date</span>
            <input className="input" type="date" value={form.expiry_date} onChange={(event) => setForm({ ...form, expiry_date: event.target.value })} />
          </label>
          <label className="md:col-span-2">
            <span className="label">Notes</span>
            <textarea className="input min-h-24" value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
          </label>
          <div className="md:col-span-2">
            <button className="btn-primary" disabled={busy} type="submit">
              {busy ? "Saving…" : "Save item"}
            </button>
          </div>
        </form>
      )}

      {uploads.length > 0 ? (
        <section className="space-y-3">
          <h2 className="font-display text-3xl text-navy-900">This batch</h2>
          {uploads.map((file) => (
            <article key={file.id} className="card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="font-medium">{file.original_name}</h3>
                  <p className="text-sm text-mist">
                    {formatBytes(file.size_bytes)} · {STAGE_LABELS[file.processing_stage] || file.processing_stage}
                  </p>
                </div>
                {file.processing_status === "error" ? (
                  <button className="btn-ghost !py-1.5" type="button" onClick={() => void reprocess(file.id)}>
                    Reprocess
                  </button>
                ) : null}
              </div>
              {file.processing_status === "queued" || file.processing_status === "processing" ? (
                <div className="indeterminate mt-4 h-1.5 rounded-full" />
              ) : null}
              {file.error_message ? <p className="mt-3 text-sm text-clay">{file.error_message}</p> : null}
              {file.result_note ? <p className="mt-3 text-sm text-pine">{file.result_note}</p> : null}
              {file.items?.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {file.items.map((item) => (
                    <Link key={item.id} className="btn-ghost !py-1.5" href={`/items/${item.id}`}>
                      {item.title}
                    </Link>
                  ))}
                </div>
              ) : null}
              {file.ocr_text ? (
                <details className="mt-3">
                  <summary className="cursor-pointer text-sm text-navy-800">Text read from the file</summary>
                  <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-paper p-3 text-xs text-ink">
                    {file.ocr_text}
                  </pre>
                </details>
              ) : null}
            </article>
          ))}
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="font-display text-3xl text-navy-900">Recent files</h2>
        {recent === null ? (
          <p className="text-sm text-mist">Loading recent files</p>
        ) : recent.length === 0 ? (
          <p className="text-sm text-mist">No files yet.</p>
        ) : (
          recent.map((file) => (
            <div key={file.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-white px-4 py-3">
              <div>
                <p className="text-sm font-medium">{file.original_name}</p>
                <p className="text-xs text-mist">{STAGE_LABELS[file.processing_status] || file.processing_status}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {file.items.map((item) => (
                  <Link key={item.id} className="text-sm text-navy-800 underline" href={`/items/${item.id}`}>
                    {item.title}
                  </Link>
                ))}
                {pendingDelete === file.id ? (
                  <>
                    <button className="btn-danger !py-1.5" type="button" disabled={busy} onClick={() => void removeFile(file.id)}>
                      Delete file
                    </button>
                    <button className="btn-ghost !py-1.5" type="button" onClick={() => setPendingDelete(null)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <button className="btn-ghost !py-1.5" type="button" onClick={() => setPendingDelete(file.id)}>
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  );
}
