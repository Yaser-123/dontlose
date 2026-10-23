"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { DeadlineCard } from "@/components/DeadlineCard";
import { ErrorNote, Loading, SuccessNote } from "@/components/States";
import { api, fileUrl } from "@/lib/api";
import { formatBytes, formatDate, formatWhen } from "@/lib/format";
import {
  CATEGORIES,
  FACT_FIELDS,
  type Category,
  type Deadline,
  type Fact,
  type ItemDetail,
  type ItemStatus,
} from "@/lib/types";

export default function ItemPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<ItemDetail | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [showRejected, setShowRejected] = useState(false);
  const [showConfirmed, setShowConfirmed] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draftValue, setDraftValue] = useState("");
  const [factField, setFactField] = useState("purchase_date");
  const [factValue, setFactValue] = useState("");
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [notesStatus, setNotesStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [pendingDocument, setPendingDocument] = useState<string | null>(null);

  function load() {
    setError("");
    api<ItemDetail>(`/items/${params.id}`)
      .then((next) => {
        setDetail(next);
      })
      .catch((reason: Error) => setError(reason.message));
  }

  useEffect(() => {
    if (params.id) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  useEffect(() => {
    if (!success) return;
    const timer = window.setTimeout(() => setSuccess(""), 2500);
    return () => window.clearTimeout(timer);
  }, [success]);

  async function act(path: string, init: RequestInit, message: string): Promise<boolean> {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const next = await api<ItemDetail>(path, init);
      if (next?.item) {
        setDetail(next);
      } else {
        load();
      }
      setSuccess(message);
      setEditing(null);
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "That change didn't save.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function updateItem(patch: Record<string, string>) {
    return act(`/items/${params.id}`, { method: "PATCH", body: JSON.stringify(patch) }, "Item updated.");
  }

  async function saveTitle(event: FormEvent) {
    event.preventDefault();
    const title = titleDraft.trim();
    if (!title) return;
    const ok = await updateItem({ title });
    if (ok) setEditingTitle(false);
  }

  async function addNote() {
    const body = noteDraft.trim();
    if (!body) return;
    setNotesStatus("saving");
    const ok = await act(
      `/items/${params.id}/notes`,
      { method: "POST", body: JSON.stringify({ body }) },
      "Note added.",
    );
    if (ok) {
      setNoteDraft("");
      setNotesStatus("saved");
    } else {
      setNotesStatus("idle");
    }
  }

  async function deadlineStatus(deadline: Deadline, status: "done" | "dismissed") {
    setBusy(true);
    setError("");
    try {
      await api(`/deadlines/${deadline.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      setSuccess(status === "done" ? "Marked done." : "Dismissed.");
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update that deadline.");
    } finally {
      setBusy(false);
    }
  }

  async function attach(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError("");
    const body = new FormData();
    Array.from(files).forEach((file) => body.append("files", file));
    body.append("item_id", params.id);
    try {
      await api("/documents", { method: "POST", body });
      setSuccess("File attached. Facts will appear when reading finishes.");
      window.setTimeout(load, 2000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not attach that file.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !detail) return <ErrorNote message={error} onRetry={load} />;
  if (!detail) return <Loading label="Opening this item" />;

  const visibleFacts = detail.facts.filter((fact) => {
    if (fact.status === "rejected") return showRejected;
    if (fact.status === "confirmed" || fact.status === "corrected") return showConfirmed;
    return true;
  });
  const confirmedCount = detail.facts.filter(
    (fact) => fact.status === "confirmed" || fact.status === "corrected",
  ).length;
  const canConfirm = detail.facts.some((fact) => fact.status === "extracted" && fact.grounded && fact.confidence === "high");

  return (
    <div className="space-y-6">
      <Link href="/items" className="text-sm text-navy-800 underline">
        Back to inventory
      </Link>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-gold">
            {CATEGORIES.find((entry) => entry.value === detail.item.category)?.label}
            {detail.item.merchant ? ` · ${detail.item.merchant}` : ""}
          </p>
          {editingTitle ? (
            <form className="mt-2 flex flex-wrap items-center gap-2" onSubmit={(event) => void saveTitle(event)}>
              <input
                className="input max-w-md font-display text-2xl text-navy-900"
                value={titleDraft}
                maxLength={160}
                required
                autoFocus
                aria-label="Item name"
                onChange={(event) => setTitleDraft(event.target.value)}
              />
              <button className="btn-primary" type="submit" disabled={busy || !titleDraft.trim()}>
                Save name
              </button>
              <button className="btn-ghost" type="button" onClick={() => setEditingTitle(false)}>
                Cancel
              </button>
            </form>
          ) : (
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h1 className="font-display text-4xl text-navy-900 md:text-5xl">{detail.item.title}</h1>
              <button
                className="btn-ghost !py-1.5"
                type="button"
                onClick={() => {
                  setTitleDraft(detail.item.title);
                  setEditingTitle(true);
                }}
              >
                Rename
              </button>
            </div>
          )}
          <p className="mt-2 text-sm text-mist">
            {detail.item.price_display || "No price"} 
            {detail.item.purchase_date ? ` · Purchased ${formatDate(detail.item.purchase_date)}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select
            className="input !w-auto"
            value={detail.item.category}
            onChange={(event) => void updateItem({ category: event.target.value as Category })}
          >
            {CATEGORIES.map((entry) => (
              <option key={entry.value} value={entry.value}>
                {entry.label}
              </option>
            ))}
          </select>
          <select
            className="input !w-auto"
            value={detail.item.status}
            onChange={(event) => void updateItem({ status: event.target.value as ItemStatus })}
          >
            <option value="active">Active</option>
            <option value="resolved">Resolved</option>
            <option value="archived">Archived</option>
          </select>
        </div>
      </header>

      {error ? <ErrorNote message={error} /> : null}
      {success ? <SuccessNote message={success} /> : null}

      {detail.gaps.length > 0 ? (
        <section className="rounded-2xl border border-gold/30 bg-gold/10 p-5">
          <h2 className="font-display text-2xl text-navy-900">Missing before a deadline can be calculated</h2>
          <ul className="mt-3 space-y-2 text-sm leading-6">
            {detail.gaps.map((gap) => (
              <li key={gap.id}>{gap.message}</li>
            ))}
          </ul>
          <StartChoice
            facts={detail.facts}
            selected={detail.item.deadline_anchor}
            busy={busy}
            onChoose={(anchor) =>
              void act(
                `/items/${params.id}/anchor`,
                { method: "POST", body: JSON.stringify({ anchor }) },
                "Start date saved.",
              )
            }
          />
        </section>
      ) : (
        <StartChoice
          facts={detail.facts}
          selected={detail.item.deadline_anchor}
          busy={busy}
          onChoose={(anchor) =>
            void act(
              `/items/${params.id}/anchor`,
              { method: "POST", body: JSON.stringify({ anchor }) },
              "Start date saved.",
            )
          }
        />
      )}

      <section className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-3 lg:col-span-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-3xl text-navy-900">Evidence</h2>
            <div className="flex gap-2">
              {canConfirm ? (
                <button
                  className="btn-primary !py-1.5"
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      `/items/${params.id}/confirm-extracted`,
                      { method: "POST" },
                      "Grounded facts confirmed.",
                    )
                  }
                >
                  Confirm grounded facts
                </button>
              ) : null}
              <button className="btn-ghost !py-1.5" type="button" onClick={() => setShowConfirmed((value) => !value)}>
                {showConfirmed ? "Hide confirmed" : `Show confirmed${confirmedCount ? ` (${confirmedCount})` : ""}`}
              </button>
              <button className="btn-ghost !py-1.5" type="button" onClick={() => setShowRejected((value) => !value)}>
                {showRejected ? "Hide rejected" : "Show rejected"}
              </button>
            </div>
          </div>
          {visibleFacts.length === 0 ? (
            <p className="text-sm text-mist">
              {detail.facts.length === 0
                ? "No facts yet."
                : "Nothing left to review. Confirmed facts stay saved."}
            </p>
          ) : null}
          {visibleFacts.map((fact) => (
            <FactRow
              key={fact.id}
              fact={fact}
              busy={busy}
              editing={editing === fact.id}
              draftValue={draftValue}
              onEdit={() => {
                setEditing(fact.id);
                setDraftValue(fact.value_text);
              }}
              onDraft={setDraftValue}
              onCancel={() => setEditing(null)}
              onConfirm={() =>
                void act(`/facts/${fact.id}`, { method: "PATCH", body: JSON.stringify({ action: "confirm" }) }, "Confirmed.")
              }
              onReject={() =>
                void act(`/facts/${fact.id}`, { method: "PATCH", body: JSON.stringify({ action: "reject" }) }, "Rejected. It won't drive a deadline.")
              }
              onSave={() =>
                void act(
                  `/facts/${fact.id}`,
                  { method: "PATCH", body: JSON.stringify({ action: "correct", value_text: draftValue }) },
                  "Correction saved.",
                )
              }
            />
          ))}
          <form
            className="card grid gap-3 p-4 md:grid-cols-[1fr_1fr_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              void act(
                `/items/${params.id}/facts`,
                { method: "POST", body: JSON.stringify({ field_name: factField, value_text: factValue }) },
                "Added from you, so it can be used in a deadline.",
              );
              setFactValue("");
            }}
          >
            <select
              className="input"
              value={factField}
              onChange={(event) => {
                setFactField(event.target.value);
                setFactValue("");
              }}
            >
              {FACT_FIELDS.map((field) => (
                <option key={field.name} value={field.name}>
                  {field.label}
                </option>
              ))}
            </select>
            <FactValueInput fieldName={factField} value={factValue} onChange={setFactValue} />
            <button className="btn-primary" disabled={busy} type="submit">
              Add fact
            </button>
          </form>
        </div>
        <div className="space-y-3 lg:col-span-2">
          <h2 className="font-display text-3xl text-navy-900">Deadlines</h2>
          {detail.deadlines.filter((deadline) => deadline.status === "open").length === 0 ? (
            <p className="text-sm leading-6 text-mist">
              No deadline can be calculated until a return window, warranty, renewal, or expiration is verified.
            </p>
          ) : (
            detail.deadlines
              .filter((deadline) => deadline.status === "open")
              .map((deadline) => (
                <DeadlineCard
                  key={deadline.id}
                  deadline={deadline}
                  onDone={(item) => void deadlineStatus(item, "done")}
                  onDismiss={(item) => void deadlineStatus(item, "dismissed")}
                />
              ))
          )}
        </div>
      </section>

      {detail.suggestions.length > 0 ? (
        <section className="space-y-3">
          <h2 className="font-display text-3xl text-navy-900">Possible matches</h2>
          {detail.suggestions.map((suggestion) => (
            <div key={suggestion.item_id} className="card flex flex-wrap items-center justify-between gap-3 p-4">
              <div>
                <p className="font-medium">{suggestion.title}</p>
                <p className="text-sm text-mist">{suggestion.reason}</p>
              </div>
              <div className="flex gap-2">
                <button
                  className="btn-primary !py-1.5"
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    void (async () => {
                      const ok = await act(
                        `/items/${params.id}/merge`,
                        { method: "POST", body: JSON.stringify({ into_item_id: suggestion.item_id }) },
                        "Merged.",
                      );
                      if (ok) router.push(`/items/${suggestion.item_id}`);
                    })();
                  }}
                >
                  Merge into this
                </button>
                <button
                  className="btn-ghost !py-1.5"
                  type="button"
                  onClick={() =>
                    void act(
                      `/items/${params.id}/links/${suggestion.item_id}/dismiss`,
                      { method: "POST" },
                      "Suggestion dismissed.",
                    )
                  }
                >
                  Not the same
                </button>
              </div>
            </div>
          ))}
        </section>
      ) : null}

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-3xl text-navy-900">Documents</h2>
          <label className="btn-ghost cursor-pointer">
            Attach a related file
            <input
              className="sr-only"
              type="file"
              accept=".png,.jpg,.jpeg,.webp,.tif,.tiff,.bmp,.pdf,image/*,application/pdf"
              multiple
              onChange={(event) => void attach(event.target.files)}
            />
          </label>
        </div>
        {detail.documents.length === 0 ? <p className="text-sm text-mist">No files linked yet.</p> : null}
        {detail.documents.map((document) => (
          <article key={document.id} className="card p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-medium">{document.original_name}</p>
                <p className="text-xs text-mist">
                  {formatBytes(document.size_bytes)}
                  {document.page_count ? ` · ${document.page_count} page${document.page_count === 1 ? "" : "s"}` : ""}
                  {` · ${document.processing_status}`}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <a className="text-sm text-navy-800 underline" href={fileUrl(document.file_path)} target="_blank" rel="noreferrer">
                  Open file
                </a>
                {pendingDocument === document.id ? (
                  <>
                    <button
                      className="btn-danger !py-1.5"
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void act(
                          `/documents/${document.id}`,
                          { method: "DELETE" },
                          "File deleted. Saved facts stay on this item.",
                        ).then(() => setPendingDocument(null))
                      }
                    >
                      Delete file
                    </button>
                    <button className="btn-ghost !py-1.5" type="button" onClick={() => setPendingDocument(null)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <button className="btn-ghost !py-1.5" type="button" onClick={() => setPendingDocument(document.id)}>
                    Delete
                  </button>
                )}
              </div>
            </div>
            {document.mime_type?.startsWith("image/") ? (
              // Local uploads are served by the API, not the Next image optimizer.
              // eslint-disable-next-line @next/next/no-img-element
              <img className="mt-3 max-h-64 rounded-xl border border-line object-contain" src={fileUrl(document.file_path)} alt={document.original_name} />
            ) : null}
            {document.error_message ? <p className="mt-3 text-sm text-clay">{document.error_message}</p> : null}
            {document.ocr_text ? (
              <details className="mt-3">
                <summary className="cursor-pointer text-sm">Text used as evidence</summary>
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-paper p-3 text-xs">{document.ocr_text}</pre>
              </details>
            ) : null}
          </article>
        ))}
      </section>

      <section className="card p-5">
        <h2 className="font-display text-2xl text-navy-900">Notes</h2>
        <div className="mt-4 space-y-3">
          {(detail.notes || []).length === 0 ? (
            <p className="text-sm text-mist">No notes yet.</p>
          ) : (
            detail.notes.map((note) => (
              <article key={note.id} className="rounded-2xl border border-line bg-paper px-4 py-3">
                <p className="whitespace-pre-wrap text-sm leading-6">{note.body}</p>
                <div className="mt-2 flex items-center justify-between gap-3">
                  <p className="text-xs text-mist">{formatWhen(note.created_at)}</p>
                  <button
                    className="text-xs text-clay underline"
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void act(`/items/${params.id}/notes/${note.id}`, { method: "DELETE" }, "Note removed.")
                    }
                  >
                    Remove
                  </button>
                </div>
              </article>
            ))
          )}
        </div>
        <label className="mt-5 block">
          <span className="label">Add a note</span>
          <textarea
            className="input mt-2 min-h-28"
            placeholder="Write a new note"
            value={noteDraft}
            onChange={(event) => {
              setNoteDraft(event.target.value);
              setNotesStatus("idle");
            }}
          />
        </label>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button className="btn-primary" type="button" disabled={busy || !noteDraft.trim()} onClick={() => void addNote()}>
            {notesStatus === "saving" ? "Saving…" : "Add note"}
          </button>
          {notesStatus === "saved" ? <p className="text-sm text-pine">Note added.</p> : null}
        </div>
      </section>

      <section>
        {confirmDelete ? (
          <div className="flex flex-wrap gap-2">
            <button
              className="btn-danger"
              type="button"
              onClick={() => {
                void api(`/items/${params.id}`, { method: "DELETE" })
                  .then(() => router.push("/items"))
                  .catch((reason: Error) => setError(reason.message));
              }}
            >
              Confirm delete
            </button>
            <button className="btn-ghost" type="button" onClick={() => setConfirmDelete(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button className="text-sm text-clay underline" type="button" onClick={() => setConfirmDelete(true)}>
            Delete this item
          </button>
        )}
      </section>
    </div>
  );
}

function latestDateFact(facts: Fact[], name: string): Fact | undefined {
  const matches = facts.filter((fact) => fact.field_name === name);
  return matches.find((fact) => fact.status !== "rejected") ?? matches[0];
}

function StartChoice({
  facts,
  selected,
  busy,
  onChoose,
}: {
  facts: Fact[];
  selected: "purchase" | "delivery" | null;
  busy: boolean;
  onChoose: (anchor: "purchase" | "delivery") => void;
}) {
  const purchase = latestDateFact(facts, "purchase_date");
  const delivery = latestDateFact(facts, "delivery_date");
  if (!purchase && !delivery) return null;
  const choice = (anchor: "purchase" | "delivery", fact: Fact, label: string) => (
    <button
      key={anchor}
      className={selected === anchor ? "btn-primary !py-1.5" : "btn-ghost !py-1.5"}
      type="button"
      disabled={busy}
      onClick={() => onChoose(anchor)}
    >
      {label} · {formatDate(fact.value_text)}
    </button>
  );
  return (
    <div className="mt-4">
      <p className="text-sm font-medium text-navy-900">Count these from</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {purchase ? choice("purchase", purchase, "Purchase date") : null}
        {delivery ? choice("delivery", delivery, "Delivery date") : null}
      </div>
    </div>
  );
}

function FactValueInput({
  fieldName,
  value,
  onChange,
  className = "",
}: {
  fieldName: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  const field = FACT_FIELDS.find((entry) => entry.name === fieldName);
  const kind = field?.kind ?? "text";
  if (kind === "date") {
    return (
      <input
        className={`input ${className}`}
        type="date"
        required
        aria-label={field?.label ?? "Date"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }
  return (
    <input
      className={`input ${className}`}
      type={kind === "number" ? "number" : "text"}
      required
      min={kind === "number" ? 1 : undefined}
      step={kind === "number" ? 1 : undefined}
      placeholder={kind === "number" ? "Number" : "Value"}
      aria-label={field?.label ?? "Value"}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

function FactRow({
  fact,
  busy,
  editing,
  draftValue,
  onEdit,
  onDraft,
  onCancel,
  onConfirm,
  onReject,
  onSave,
}: {
  fact: Fact;
  busy: boolean;
  editing: boolean;
  draftValue: string;
  onEdit: () => void;
  onDraft: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
  onReject: () => void;
  onSave: () => void;
}) {
  const field = FACT_FIELDS.find((entry) => entry.name === fact.field_name);
  const dateDraft = /^\d{4}-\d{2}-\d{2}$/.test(draftValue) ? draftValue : "";
  return (
    <article className="card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="label">{fact.label}</p>
          <p className="text-lg text-navy-900">{field?.kind === "date" ? formatDate(fact.value_text) : fact.value_text}</p>
          <p className="mt-1 text-xs uppercase tracking-wider text-mist">
            {fact.status}
            {fact.quote === "Entered manually"
              ? " · entered by you"
              : fact.grounded
                ? " · found in the file"
                : fact.status === "extracted"
                  ? " · not found in the file"
                  : ""}
          </p>
        </div>
        {fact.status !== "rejected" ? (
          <div className="flex flex-wrap gap-2">
            <button className="btn-ghost !py-1.5" type="button" disabled={busy} onClick={onConfirm}>
              Confirm
            </button>
            <button className="btn-ghost !py-1.5" type="button" disabled={busy} onClick={onEdit}>
              Correct
            </button>
            <button className="btn-ghost !py-1.5" type="button" disabled={busy} onClick={onReject}>
              Reject
            </button>
          </div>
        ) : null}
      </div>
      <blockquote className="mt-3 border-l-2 border-gold/60 pl-3 text-sm italic text-ink/80">
        {fact.quote === "Entered manually"
          ? "You typed this in."
          : fact.quote || "No supporting excerpt was found in the file."}
        {fact.document_name ? <span className="mt-1 block text-xs not-italic text-mist">From {fact.document_name}</span> : null}
      </blockquote>
      {editing ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <FactValueInput
            fieldName={fact.field_name}
            value={field?.kind === "date" ? dateDraft : draftValue}
            onChange={onDraft}
            className="max-w-xs"
          />
          <button className="btn-primary !py-1.5" type="button" disabled={busy} onClick={onSave}>
            Save
          </button>
          <button className="btn-ghost !py-1.5" type="button" onClick={onCancel}>
            Cancel
          </button>
        </div>
      ) : null}
    </article>
  );
}
