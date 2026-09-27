import type { MapLocation } from "../../api/types";
import { formatNumber, operatorLabelOrNull } from "../../lib/format";
import { IconClose, IconLocate } from "../../ui/icons";

function formatDistance(distanceM: number | null): string {
  if (distanceM === null) return "فاصله نامشخص";
  if (distanceM < 1000) return `${formatNumber(distanceM)} متر`;
  return `${formatNumber(Math.round((distanceM / 1000) * 10) / 10)} کیلومتر`;
}

export function NearbyStations({
  items,
  loading,
  error,
  onSelect,
  onClose,
}: {
  items: MapLocation[];
  loading: boolean;
  error: string | null;
  onSelect: (location: MapLocation) => void;
  onClose: () => void;
}) {
  return (
    <section className="nearby-panel" aria-labelledby="nearby-title" aria-live="polite">
      <header>
        <span className="nearby-heading-icon"><IconLocate /></span>
        <div>
          <h2 id="nearby-title">نزدیک‌ترین ایستگاه‌ها</h2>
          <p>{loading ? "در حال پیدا کردن…" : `${formatNumber(items.length)} ایستگاه نزدیک شما`}</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="بستن فهرست نزدیک‌ترین ایستگاه‌ها">
          <IconClose />
        </button>
      </header>
      {error && <p className="nearby-message error">{error}</p>}
      {!error && !loading && items.length === 0 && (
        <p className="nearby-message">در شعاع ۱۰۰ کیلومتری ایستگاهی با این فیلترها پیدا نشد.</p>
      )}
      <ol className="nearby-list">
        {items.map((location, index) => (
          <li key={location.id}>
            <button type="button" onClick={() => onSelect(location)}>
              <span className="nearby-rank">{formatNumber(index + 1)}</span>
              <span className="nearby-copy">
                <strong>{location.name}</strong>
                {/* Phase 1: بدون fallback به وضعیت شارژ؛ فقط شهر/اپراتور (Unknown مخفی) */}
                <small>{[location.city, operatorLabelOrNull(location.operator_name)].filter(Boolean).join(" · ")}</small>
              </span>
              <span className="nearby-distance">{formatDistance(location.distance_m)}</span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
