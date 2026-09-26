import { useEffect, useRef } from "react";
import type { LocationDetail, VehicleVariant } from "../../api/types";
import { formatNumber, formatPower, formatWhen, sourceLabel } from "../../lib/format";
import { stationCompatibility } from "../../lib/vehicles";
import { ConnectorMark } from "../../ui/ConnectorMark";
import { IconClose } from "../../ui/icons";
import { ChargeEstimate } from "./ChargeEstimate";

function plugsOf(location: LocationDetail) {
  const seen = new Map<string, { key: string; standard: string; format: string | null; label: string }>();
  for (const evse of location.evses) {
    for (const connector of evse.connectors) {
      const cable = connector.standard === "TYPE_2" && connector.format?.toUpperCase() === "CABLE";
      const key = cable ? "TYPE_2:CABLE" : connector.standard;
      if (seen.has(key)) continue;
      seen.set(key, {
        key,
        standard: connector.standard,
        format: connector.format,
        label: cable ? `${connector.standard_label} کابلی` : connector.standard_label,
      });
    }
  }
  return [...seen.values()];
}

function safeHttp(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.toString();
  } catch {
    return null;
  }
  return null;
}

export function DetailPanel({
  location,
  loading,
  error,
  vehicle = null,
  onClose,
}: {
  location: LocationDetail | undefined;
  loading: boolean;
  error: string | null;
  vehicle?: VehicleVariant | null;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (error) errorRef.current?.focus();
    else if (headingRef.current) headingRef.current.focus();
    else closeRef.current?.focus();
  }, [error, location?.id]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape" || document.getElementById("sources-dialog") || document.getElementById("vehicle-dialog")) return;
      event.preventDefault();
      onCloseRef.current();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const site = location ? safeHttp(location.website) : null;
  const plugs = location ? plugsOf(location) : [];
  const compatibility = location
    ? stationCompatibility(
        location.evses.flatMap((evse) => evse.connectors.map((connector) => connector.standard)),
        vehicle,
      )
    : null;

  return (
    <aside
      className="detail"
      ref={panelRef}
      tabIndex={-1}
      aria-busy={loading}
      aria-labelledby={location ? "location-title" : "detail-label"}
    >
      <div className="detail-bar">
        <p id="detail-label">جزئیات ایستگاه</p>
        <button type="button" ref={closeRef} onClick={onClose}>
          <IconClose />
          بستن
        </button>
      </div>
      {loading && (
        <div className="skeleton" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      )}
      {loading && <p className="visually-hidden">در حال دریافت جزئیات</p>}
      {error && (
        <p className="error" role="alert" tabIndex={-1} ref={errorRef}>
          {error}
        </p>
      )}
      {location && (
        <div className="detail-body">
          <div className={`status status-${location.availability}`}>{location.availability_label}</div>
          <h2 id="location-title" ref={headingRef} tabIndex={-1}>
            {location.name}
          </h2>
          {compatibility === "yes" && vehicle && <p className="compat">سازگار با {vehicle.display_name}</p>}
          {compatibility === "no" && vehicle && (
            <p className="compat is-off">این جایگاه با {vehicle.display_name} درگاه مشترک ندارد.</p>
          )}
          {compatibility === "unknown" && vehicle && (
            <p className="compat is-off">درگاه این جایگاه ثبت نشده و سازگاری با {vehicle.display_name} مشخص نیست.</p>
          )}
          {compatibility === "yes" && vehicle && <ChargeEstimate vehicle={vehicle} location={location} />}
          {location.name_en && <p className="muted en">{location.name_en}</p>}
          <p className="address">{location.address || [location.city, location.province].filter(Boolean).join("، ") || "آدرس ثبت نشده"}</p>
          {plugs.length > 0 && (
            <div className="chips plugs">
              {plugs.map((plug) => (
                <span key={plug.key}>
                  <ConnectorMark standard={plug.standard} format={plug.format} />
                  {plug.label}
                </span>
              ))}
            </div>
          )}
          <div className="chips">
            {location.operator_name && <span>{location.operator_name}</span>}
            <span>{formatPower(location.max_power_kw)}</span>
            {location.is_24_7 && <span>شبانه‌روزی</span>}
            {location.is_reservable && <span>قابل رزرو</span>}
            {location.is_public === false && <span>غیرعمومی</span>}
          </div>
          {location.notes.length > 0 && (
            <section className="source-notes">
              <h3>یادداشت‌ها</h3>
              {location.notes.map((note) => (
                <p className="note" key={`${note.source_code}-${note.kind}-${note.text}`}>
                  {note.text}
                  <span className="muted">
                    {note.kind === "notice" ? `اطلاع کاربر · ${sourceLabel(note.source_code)}` : sourceLabel(note.source_code)}
                    {note.observed_at ? ` · ${formatWhen(note.observed_at)}` : ""}
                  </span>
                </p>
              ))}
            </section>
          )}
          {location.is_stale && (
            <p className="note">وضعیت زنده منقضی شده و این ایستگاه به‌عنوان آزاد نشان داده نمی‌شود.</p>
          )}
          {location.hours_summary && <p>ساعت کار: {location.hours_summary}</p>}
          {location.price && (
            <div className="price">
              <strong>
                {location.price.is_free
                  ? "رایگان"
                  : `${formatNumber(location.price.amount_toman)} تومان / کیلووات‌ساعت`}
              </strong>
              <span>
                {location.price.label ? `${location.price.label} · ` : ""}
                مشاهده {formatWhen(location.price.observed_at)} از {sourceLabel(location.price.source_code)}
              </span>
              {location.price.varies && <span>قیمت دستگاه‌های این محل یکسان نیست؛ آخرین مشاهده نشان داده شده.</span>}
            </div>
          )}
          {location.facilities.length > 0 && (
            <div className="chips quiet">
              {location.facilities.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          )}
          {location.images[0] && (
            <img
              src={location.images[0]}
              alt={location.name}
              onError={(event) => {
                event.currentTarget.hidden = true;
              }}
            />
          )}
          <div className="actions">
            <a
              className="primary"
              href={`https://www.google.com/maps/dir/?api=1&destination=${location.lat},${location.lng}`}
              target="_blank"
              rel="noreferrer"
            >
              مسیریابی
              <span className="visually-hidden">، در زبانه جدید</span>
            </a>
            <a
              href={`https://www.openstreetmap.org/?mlat=${location.lat}&mlon=${location.lng}#map=17/${location.lat}/${location.lng}`}
              target="_blank"
              rel="noreferrer"
            >
              نقشه بیرونی
              <span className="visually-hidden">، در زبانه جدید</span>
            </a>
            {site && (
              <a href={site} target="_blank" rel="noreferrer">
                وب‌سایت
                <span className="visually-hidden">، در زبانه جدید</span>
              </a>
            )}
            {location.phone && (
              <a href={`tel:${location.phone}`} dir="ltr">
                {location.phone}
              </a>
            )}
          </div>
          <section>
            <h3>تجهیزات</h3>
            {location.evses.length === 0 && <p className="muted">تجهیزی برای نمایش ثبت نشده.</p>}
            {location.evses.map((evse) => (
              <article key={evse.id} className="evse">
                <header>
                  <strong>{evse.external_id}</strong>
                  <span className={`status status-${evse.is_stale ? "stale" : evse.status.toLowerCase()}`}>{evse.status_label}</span>
                </header>
                <p className="muted">
                  {sourceLabel(evse.source_code)}
                  {evse.max_power_kw ? ` · ${formatPower(evse.max_power_kw)}` : ""}
                  {evse.status_kind === "operational" ? " · وضعیت عملیاتی، نه زنده" : ""}
                  {evse.reported_status_label && evse.reported_status !== evse.status
                    ? ` · وضعیت خام منبع: ${evse.reported_status_label}`
                    : ""}
                </p>
                {evse.counts && (
                  <p className="muted">
                    کانکتورهای اعلام‌شده: {formatNumber(evse.counts.total || 0)} · آزاد{" "}
                    {formatNumber(evse.counts.available || 0)} · در حال شارژ {formatNumber(evse.counts.charging || 0)}
                  </p>
                )}
                <ul>
                  {evse.connectors.map((connector) => (
                    <li key={connector.id}>
                      <ConnectorMark standard={connector.standard} format={connector.format} />
                      <b>{connector.standard_label}</b>
                      <span>{connector.power_type || "نوع توان نامشخص"}</span>
                      <span>{connector.max_power_kw ? formatPower(connector.max_power_kw) : "توان نامشخص"}</span>
                      <span>{connector.status_label || "بدون وضعیت"}</span>
                    </li>
                  ))}
                </ul>
                {evse.connectors.length === 0 && <p className="muted">جزئیات کانکتور هنوز دریافت نشده.</p>}
              </article>
            ))}
          </section>
          <section>
            <h3>منابع و مجوز</h3>
            {location.sources.map((source) => (
              <p key={`${source.code}-${source.external_id}`} className="source-line">
                <b>{source.name}</b>
                <span>شناسه {source.external_id}</span>
                <span>آخرین مشاهده {formatWhen(source.last_seen_at)}</span>
                {source.attribution && <span>{source.attribution}</span>}
              </p>
            ))}
            <p className="muted">امتیاز کیفیت داده: {location.data_quality_score == null ? "—" : formatNumber(location.data_quality_score)}</p>
          </section>
        </div>
      )}
    </aside>
  );
}
