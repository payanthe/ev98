import { formatNumber } from "../../lib/format";

export function MapStatus({
  ready,
  loading,
  updating,
  count,
  truncated,
  empty,
  filtered,
  scope = null,
  error,
  notice,
  onRetry,
  onClear,
  onDismissNotice,
}: {
  ready: boolean;
  loading: boolean;
  updating: boolean;
  count: number;
  truncated: boolean;
  empty: boolean;
  filtered: boolean;
  scope?: string | null;
  error: string | null;
  notice: string | null;
  onRetry: () => void;
  onClear: () => void;
  onDismissNotice: () => void;
}) {
  const counted = scope
    ? `${formatNumber(count)} ایستگاه سازگار با ${scope}`
    : `${formatNumber(count)} ایستگاه`;
  const headline = !ready
    ? "نقشه در حال آماده‌شدن است"
    : loading
      ? "در حال بارگذاری ایستگاه‌ها"
      : empty
        ? filtered
          ? "با این فیلترها ایستگاهی در این محدوده نیست."
          : "در این محدوده ایستگاهی ثبت نشده."
        : truncated
          ? `${counted} در این نما. برای دیدن بقیه بزرگ‌نمایی کنید.`
          : updating
            ? `در حال به‌روزرسانی… ${counted}`
            : `${counted} در این نما`;

  const showHeadline = !(error && count === 0);

  return (
    <div className="map-status">
      {showHeadline && (
        <p>
          {(loading || updating) && <span className="spinner" aria-hidden="true" />}
          {headline}
        </p>
      )}
      {empty && filtered && (
        <button type="button" onClick={onClear}>
          پاک کردن فیلترها
        </button>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
          <button type="button" onClick={onRetry}>
            تلاش دوباره
          </button>
        </p>
      )}
      {notice && (
        <p role="alert">
          {notice}
          <button type="button" onClick={onDismissNotice}>
            بستن
          </button>
        </p>
      )}
    </div>
  );
}
