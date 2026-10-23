import Link from "next/link";

import { daysLabel, formatDate, severityClass } from "@/lib/format";
import type { Deadline } from "@/lib/types";

export function DeadlineCard({
  deadline,
  onDone,
  onDismiss,
}: {
  deadline: Deadline;
  onDone?: (deadline: Deadline) => void;
  onDismiss?: (deadline: Deadline) => void;
}) {
  return (
    <article className={`rounded-2xl border p-4 ${severityClass(deadline.severity)}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.16em]">{deadline.label}</p>
          <h3 className="mt-1 font-display text-2xl text-navy-900">
            <Link href={`/items/${deadline.item_id}`} className="hover:underline">
              {deadline.item_title}
            </Link>
          </h3>
          <p className="mt-1 text-sm">
            {formatDate(deadline.due_date)} · {daysLabel(deadline.days_remaining)}
          </p>
        </div>
        {deadline.provisional ? (
          <span className="shrink-0 rounded-full border border-gold/40 bg-white px-2 py-1 text-[11px] uppercase tracking-wider text-gold">
            Needs confirmation
          </span>
        ) : (
          <span className="shrink-0 rounded-full border border-pine/20 bg-white px-2 py-1 text-[11px] uppercase tracking-wider text-pine">
            Confirmed
          </span>
        )}
      </div>
      <p className="mt-3 text-sm leading-6 text-ink/80">{deadline.basis}</p>
      {onDone || onDismiss ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {onDone ? (
            <button className="btn-primary !py-1.5" type="button" onClick={() => onDone(deadline)}>
              Mark done
            </button>
          ) : null}
          {onDismiss ? (
            <button className="btn-ghost !py-1.5" type="button" onClick={() => onDismiss(deadline)}>
              Dismiss
            </button>
          ) : null}
          <Link className="btn-ghost !py-1.5" href={`/reminders?item=${deadline.item_id}&deadline=${deadline.id}`}>
            Remind me
          </Link>
        </div>
      ) : null}
    </article>
  );
}
