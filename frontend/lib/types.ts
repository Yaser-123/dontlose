export type Category = "receipt" | "warranty" | "subscription" | "renewal" | "document" | "other";
export type ItemStatus = "active" | "resolved" | "archived";
export type Severity = "overdue" | "critical" | "high" | "medium" | "low";

export type Deadline = {
  id: string;
  item_id: string;
  item_title: string;
  merchant: string | null;
  kind: string;
  label: string;
  due_date: string;
  basis: string;
  provisional: boolean;
  status: "open" | "done" | "dismissed";
  severity: Severity;
  days_remaining: number;
};

export type Fact = {
  id: string;
  field_name: string;
  label: string;
  value_text: string;
  quote: string | null;
  confidence: "high" | "medium" | "low";
  status: "extracted" | "confirmed" | "corrected" | "rejected";
  grounded: boolean;
  document_id: string | null;
  document_name: string | null;
};

export type Gap = { id: string; message: string };

export type DocumentInfo = {
  id: string;
  original_name: string;
  mime_type: string | null;
  size_bytes: number;
  page_count: number | null;
  processing_status: string;
  processing_stage: string;
  error_message: string | null;
  result_note: string | null;
  created_at: string;
  processed_at: string | null;
  file_path: string;
  ocr_text?: string | null;
  items: { id: string; title: string }[];
};

export type Suggestion = {
  item_id: string;
  title: string;
  merchant: string | null;
  reason: string;
};

export type ItemSummary = {
  id: string;
  title: string;
  merchant: string | null;
  category: Category;
  status: ItemStatus;
  deadline_anchor: "purchase" | "delivery" | null;
  notes: string;
  price_display: string | null;
  purchase_date: string | null;
  created_at: string;
  updated_at: string;
  needs_review: boolean;
  open_deadline_count: number;
  next_deadline: Deadline | null;
};

export type ItemNote = {
  id: string;
  body: string;
  created_at: string;
};

export type ItemDetail = {
  item: ItemSummary;
  facts: Fact[];
  deadlines: Deadline[];
  gaps: Gap[];
  documents: DocumentInfo[];
  suggestions: Suggestion[];
  notes: ItemNote[];
  confirmed_count?: number;
};

export type Reminder = {
  id: string;
  item_id: string | null;
  item_title: string | null;
  deadline_id: string | null;
  remind_at: string;
  message: string;
  status: "scheduled" | "seen" | "dismissed";
  created_at: string;
};

export type Dashboard = {
  today: string;
  counts: {
    active_items: number;
    open_deadlines: number;
    needs_review: number;
    overdue: number;
  };
  alerts: Deadline[];
  upcoming: Deadline[];
  needs_review: ItemSummary[];
  recent_items: ItemSummary[];
};

export type Health = {
  ok: boolean;
  database: boolean;
  tesseract: { available: boolean; version: string | null; path: string | null };
  ollama: { available: boolean; model: string; model_present: boolean; error: string | null };
  windows_notifications: boolean;
};

export const CATEGORIES: { value: Category; label: string }[] = [
  { value: "receipt", label: "Receipt" },
  { value: "warranty", label: "Warranty" },
  { value: "subscription", label: "Subscription" },
  { value: "renewal", label: "Renewal" },
  { value: "document", label: "Document" },
  { value: "other", label: "Other" },
];

export const FACT_FIELDS: { name: string; label: string; kind: "date" | "number" | "text" }[] = [
  { name: "merchant", label: "Merchant", kind: "text" },
  { name: "price", label: "Price", kind: "text" },
  { name: "currency", label: "Currency", kind: "text" },
  { name: "purchase_date", label: "Purchase date", kind: "date" },
  { name: "delivery_date", label: "Delivery date", kind: "date" },
  { name: "return_days", label: "Return window (days)", kind: "number" },
  { name: "warranty_months", label: "Warranty length (months)", kind: "number" },
  { name: "warranty_years", label: "Warranty length (years)", kind: "number" },
  { name: "warranty_days", label: "Warranty length (days)", kind: "number" },
  { name: "warranty_end", label: "Warranty end", kind: "date" },
  { name: "renewal_date", label: "Renewal date", kind: "date" },
  { name: "renewal_period_months", label: "Renewal interval (months)", kind: "number" },
  { name: "expiry_date", label: "Expiration date", kind: "date" },
];

export const STAGE_LABELS: Record<string, string> = {
  queued: "Waiting to be read",
  reading: "Reading the file",
  model: "Asking Gemma what is actually written",
  saving: "Checking every value against the text",
  ready: "Saved on this computer",
  error: "Needs attention",
};
