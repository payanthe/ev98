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
