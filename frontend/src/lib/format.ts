const numberFormat = new Intl.NumberFormat("fa-IR");
const dateFormat = new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium", timeStyle: "short" });

export function formatNumber(value: number): string {
  return numberFormat.format(value);
}

export function formatWhen(value: string | null | undefined): string {
  if (!value) return "نامشخص";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "نامشخص";
  return dateFormat.format(date);
}

export function formatPower(kw: number | null | undefined): string {
  if (kw == null) return "توان نامشخص";
  return `${formatNumber(kw)} کیلووات`;
}

export function sourceLabel(code: string): string {
  if (code === "sharinet") return "شارینت";
  if (code === "ocm") return "OCM";
  if (code === "abrp") return "ABRP";
  return code;
}

export function isUnknownOperator(name: string | null | undefined): boolean {
  if (!name) return true;
  const normalized = name.trim().toLowerCase();
  return normalized === "" || normalized === "unknown" || normalized === "unknown operator";
}

/** Short Persian brand names for known network operators. */
function canonicalizeOperatorName(name: string): string {
  const trimmed = name.trim();
  if (/ایکس\s*ویژن|xvision|xv\s*go/i.test(trimmed)) return "ایکس ویژن";
  return trimmed;
}

/** For compact lists: hide unknown operators entirely. */
export function operatorLabelOrNull(name: string | null | undefined): string | null {
  if (isUnknownOperator(name)) return null;
  return canonicalizeOperatorName(name!);
}

/** For detail views: show a Persian fallback instead of English placeholders. */
export function formatOperatorName(name: string | null | undefined): string {
  if (isUnknownOperator(name)) return "نامشخص";
  return canonicalizeOperatorName(name!);
}
