import { useEffect, useRef, useState } from "react";
// Phase 1: useId فقط برای پنل منابع بود
// import { useEffect, useId, useRef, useState } from "react";
import type { LocationDetail, VehicleVariant } from "../../api/types";
import { formatNumber, formatOperatorName, formatPower } from "../../lib/format";
// Phase 1: formatWhen و sourceLabel برای نمایش منبع/مجوز به کاربر استفاده نمی‌شوند
// import { formatNumber, formatPower, formatWhen, sourceLabel } from "../../lib/format";
import { stationCompatibility } from "../../lib/vehicles";
import { ConnectorMark } from "../../ui/ConnectorMark";
import { IconChevron, IconClose, IconOperator } from "../../ui/icons";
// Phase 1: آیکن منابع/مجوز مخفی
// import { IconChevron, IconClose, IconOperator, IconSources } from "../../ui/icons";
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

function powerTypeLabel(value: string | null): string {
  if (!value) return "نوع جریان نامشخص";
  const normalized = value.toUpperCase();
  if (normalized.includes("DC")) return "شارژ سریع DC";
  if (normalized.includes("AC")) return "شارژ AC";
  return value.replaceAll("_", " ");
}

// Phase 1: کلاس CSS وضعیت زنده فعلاً لازم نیست؛ برای فاز بعد نگه داشته شده
// function statusClass(value: string | null | undefined): string {
//   return (value || "unknown").toLowerCase().replaceAll(" ", "_");
// }

function LocationGallery({ images, name, locationId }: { images: string[]; name: string; locationId: string }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [failedImages, setFailedImages] = useState<Set<string>>(() => new Set());
  const visibleImages = images.filter((image) => !failedImages.has(image));

  useEffect(() => {
    setActiveIndex(0);
    setFailedImages(new Set());
  }, [locationId]);

  useEffect(() => {
    if (activeIndex >= visibleImages.length) setActiveIndex(Math.max(0, visibleImages.length - 1));
  }, [activeIndex, visibleImages.length]);

  if (visibleImages.length === 0) return null;

  const activeImage = visibleImages[activeIndex];
  const selectRelative = (offset: number) => {
    setActiveIndex((current) => (current + offset + visibleImages.length) % visibleImages.length);
  };

  return (
    <figure
      className="location-gallery"
      aria-label={`تصاویر ${name}`}
      onKeyDown={(event) => {
        if (visibleImages.length < 2) return;
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          selectRelative(1);
        } else if (event.key === "ArrowRight") {
          event.preventDefault();
          selectRelative(-1);
        }
      }}
    >
      <div className="location-gallery-stage">
        <img
          className="location-gallery-image"
          src={activeImage}
          alt={`${name}، تصویر ${formatNumber(activeIndex + 1)} از ${formatNumber(visibleImages.length)}`}
          decoding="async"
          onError={() => setFailedImages((current) => new Set(current).add(activeImage))}
        />
        {visibleImages.length > 1 && (
          <>
            <button type="button" className="gallery-control gallery-previous" aria-label="تصویر قبلی" onClick={() => selectRelative(-1)}>
              <IconChevron direction="previous" />
            </button>
            <button type="button" className="gallery-control gallery-next" aria-label="تصویر بعدی" onClick={() => selectRelative(1)}>
              <IconChevron direction="next" />
            </button>
          </>
        )}
        <figcaption aria-live="polite">
          {formatNumber(activeIndex + 1)} / {formatNumber(visibleImages.length)}
        </figcaption>
      </div>
      {visibleImages.length > 1 && (
        <div className="location-gallery-thumbnails" aria-label="انتخاب تصویر">
          {visibleImages.map((image, index) => (
            <button
              type="button"
              key={image}
              aria-label={`نمایش تصویر ${formatNumber(index + 1)}`}
              aria-pressed={index === activeIndex}
              onClick={() => setActiveIndex(index)}
            >
              <img src={image} alt="" loading="lazy" decoding="async" />
            </button>
          ))}
        </div>
      )}
    </figure>
  );
}

export function DetailPanel({
  location,
  loading,
  error,
  vehicle = null,
  onClose,
  onNextNearby,
}: {
  location: LocationDetail | undefined;
  loading: boolean;
  error: string | null;
  vehicle?: VehicleVariant | null;
  onClose: () => void;
  onNextNearby?: () => void;
}) {
  const panelRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  // Phase 1: پنل منابع و مجوز مخفی
  // const sourcesToggleRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  // const [sourcesOpen, setSourcesOpen] = useState(false);
  // const sourcesPanelId = useId();
  // const sourcesTitleId = useId();

  // useEffect(() => {
  //   setSourcesOpen(false);
  // }, [location?.id]);

  useEffect(() => {
    if (error) errorRef.current?.focus();
    else if (headingRef.current) headingRef.current.focus();
    else closeRef.current?.focus();
  }, [error, location?.id]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape" || document.getElementById("sources-dialog") || document.getElementById("vehicle-dialog")) return;
      event.preventDefault();
      // Phase 1: بستن پنل منابع حذف شد
      // if (sourcesOpen) {
      //   setSourcesOpen(false);
      //   sourcesToggleRef.current?.focus();
      //   return;
      // }
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
  const equipmentSummary = location
    ? {
        connectors: location.evses.reduce(
          (total, evse) => total + (evse.counts?.total ?? evse.connectors.length),
          0,
        ),
      }
    : { connectors: 0 };
  // Phase 1: شمارش کانکتور آزاد / وضعیت زنده نمایش داده نمی‌شود
  // const equipmentSummary = location
  //   ? location.evses.reduce(
  //       (summary, evse) => {
  //         summary.connectors += evse.counts?.total ?? evse.connectors.length;
  //         if (evse.counts?.available != null) {
  //           summary.available += evse.counts.available;
  //           summary.availabilityKnown = true;
  //         } else if (evse.connectors.some((connector) => connector.status != null)) {
  //           summary.available += evse.connectors.filter((connector) => connector.status?.toUpperCase() === "AVAILABLE").length;
  //           summary.availabilityKnown = true;
  //         }
  //         return summary;
  //       },
  //       { connectors: 0, available: 0, availabilityKnown: false },
  //     )
  //   : { connectors: 0, available: 0, availabilityKnown: false };

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
        <div className="detail-bar-actions">
          {/* Phase 1: دکمه و پنل «منابع و مجوز» مخفی — به کاربر نشان داده نمی‌شود */}
          {/*
          {location && (
            <button
              type="button"
              ref={sourcesToggleRef}
              className="detail-sources-toggle"
              aria-label="منابع و مجوز"
              aria-expanded={sourcesOpen}
              aria-controls={sourcesOpen ? sourcesPanelId : undefined}
              onClick={() => setSourcesOpen((open) => !open)}
            >
              <IconSources />
            </button>
          )}
          */}
          {onNextNearby && (
            <button type="button" className="detail-next-nearby" onClick={onNextNearby}>
              ایستگاه نزدیک بعدی
            </button>
          )}
          <button type="button" ref={closeRef} className="detail-close" aria-label="بستن" onClick={onClose}>
            <IconClose />
          </button>
        </div>
      </div>
      {/*
      {location && sourcesOpen && (
        <section
          id={sourcesPanelId}
          className="detail-sources-panel"
          role="region"
          aria-labelledby={sourcesTitleId}
        >
          <div className="detail-sources-head">
            <h3 id={sourcesTitleId}>منابع و مجوز</h3>
            <button type="button" className="detail-sources-close" aria-label="بستن منابع و مجوز" onClick={() => setSourcesOpen(false)}>
              <IconClose />
            </button>
          </div>
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
      )}
      */}
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
          {/* Phase 1: بج وضعیت ایستگاه (آزاد / در حال شارژ / …) مخفی — فقط محل */}
          {/* <div className={`status status-${location.availability}`}>{location.availability_label}</div> */}
          <h2 id="location-title" ref={headingRef} tabIndex={-1}>
            {location.name}
          </h2>
          {location.operator_name && (
            <p className="operator-badge">
              <span className="operator-badge-icon" aria-hidden="true">
                <IconOperator />
              </span>
              <span className="operator-badge-copy">
                <span className="operator-badge-label">اپراتور شبکه</span>
                <strong className="operator-badge-name">{formatOperatorName(location.operator_name)}</strong>
              </span>
            </p>
          )}
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
            <span>{formatPower(location.max_power_kw)}</span>
            {location.open_now != null && location.open_now_label && (
              <span className={`hours-chip is-${location.open_now ? "open" : "closed"}`}>{location.open_now_label}</span>
            )}
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
                  {/* Phase 1: نام منبع و attribution در یادداشت مخفی */}
                  {/*
                  <span className="muted">
                    {note.kind === "notice" ? `اطلاع کاربر · ${sourceLabel(note.source_code)}` : sourceLabel(note.source_code)}
                    {note.observed_at ? ` · ${formatWhen(note.observed_at)}` : ""}
                  </span>
                  */}
                </p>
              ))}
            </section>
          )}
          {/* Phase 1: هشدار وضعیت زنده منقضی مخفی */}
          {/*
          {location.is_stale && (
            <p className="note">وضعیت زنده منقضی شده و این ایستگاه به‌عنوان آزاد نشان داده نمی‌شود.</p>
          )}
          */}
          {(location.hours_label || location.hours_summary) && (
            <p className="hours-line">ساعت کار: {location.hours_label || location.hours_summary}</p>
          )}
          {location.price && (
            <div className="price">
              <strong>
                {location.price.is_free
                  ? "رایگان"
                  : `${formatNumber(location.price.amount_toman)} تومان / کیلووات‌ساعت`}
              </strong>
              {/* Phase 1: برچسب منبع قیمت مخفی؛ فقط برچسب خود قیمت در صورت وجود */}
              {location.price.label && <span>{location.price.label}</span>}
              {/*
              <span>
                {location.price.label ? `${location.price.label} · ` : ""}
                مشاهده {formatWhen(location.price.observed_at)} از {sourceLabel(location.price.source_code)}
              </span>
              */}
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
          <LocationGallery images={location.images} name={location.name} locationId={location.id} />
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
          <section className="equipment-section" aria-labelledby="equipment-title">
            <div className="equipment-heading">
              <div>
                <h3 id="equipment-title">تجهیزات</h3>
                {location.evses.length > 0 && (
                  <p>
                    {formatNumber(location.evses.length)} دستگاه · {formatNumber(equipmentSummary.connectors)} کانکتور
                  </p>
                )}
              </div>
              {/* Phase 1: برچسب «N کانکتور آزاد» مخفی — وضعیت زنده در فاز بعدی */}
              {/*
              {equipmentSummary.availabilityKnown && (
                <span className={`equipment-available${equipmentSummary.available === 0 ? " is-empty" : ""}`}>
                  {equipmentSummary.available > 0
                    ? `${formatNumber(equipmentSummary.available)} کانکتور آزاد`
                    : "کانکتور آزادی گزارش نشده"}
                </span>
              )}
              */}
            </div>
            {location.evses.length === 0 && <p className="muted">تجهیزی برای نمایش ثبت نشده.</p>}
            {location.evses.map((evse, evseIndex) => (
              <article key={evse.id} className="evse">
                <header className="evse-head">
                  <div className="evse-title">
                    <span className="evse-index" aria-hidden="true">{formatNumber(evseIndex + 1)}</span>
                    <div>
                      <strong>شارژر {formatNumber(evseIndex + 1)}</strong>
                      <span>{evse.connectors.length > 0 ? `${formatNumber(evse.connectors.length)} نوع اتصال` : "بدون جزئیات اتصال"}</span>
                    </div>
                  </div>
                  {/* Phase 1: وضعیت شارژر (آزاد/اشغال/…) مخفی */}
                  {/* <span className={`status status-${evse.is_stale ? "stale" : statusClass(evse.status)}`}>{evse.status_label}</span> */}
                </header>
                <dl className="evse-facts">
                  <div>
                    <dt>توان</dt>
                    <dd>{formatPower(evse.max_power_kw)}</dd>
                  </div>
                  {/* Phase 1: دسترسی زنده و آخرین وضعیت مخفی — فقط محل و مشخصات سخت‌افزاری */}
                  {/*
                  <div>
                    <dt>دسترسی</dt>
                    <dd>
                      {evse.counts?.available != null && evse.counts.total != null
                        ? `${formatNumber(evse.counts.available)} از ${formatNumber(evse.counts.total)} آزاد`
                        : evse.status_label}
                    </dd>
                  </div>
                  <div>
                    <dt>آخرین وضعیت</dt>
                    <dd>{formatWhen(evse.status_updated_at)}</dd>
                  </div>
                  */}
                </dl>
                <ul className="connector-list" aria-label={`کانکتورهای شارژر ${formatNumber(evseIndex + 1)}`}>
                  {evse.connectors.map((connector) => (
                    <li key={connector.id}>
                      <ConnectorMark standard={connector.standard} format={connector.format} />
                      <span className="connector-copy">
                        <b>{connector.standard_label}</b>
                        <small>{powerTypeLabel(connector.power_type)} · {formatPower(connector.max_power_kw)}</small>
                      </span>
                      {/* Phase 1: وضعیت کانکتور مخفی */}
                      {/*
                      <span className={`connector-status status-${statusClass(connector.status)}`}>
                        {connector.status_label || "وضعیت نامشخص"}
                      </span>
                      */}
                    </li>
                  ))}
                </ul>
                {evse.connectors.length === 0 && <p className="muted">جزئیات کانکتور هنوز دریافت نشده.</p>}
                {/* Phase 1: جزئیات فنی و منبع مخفی — شناسه/نام منبع به کاربر نشان داده نمی‌شود */}
                {/*
                <details className="evse-technical">
                  <summary>جزئیات فنی و منبع</summary>
                  <dl>
                    <div><dt>شناسه دستگاه</dt><dd dir="ltr">{evse.external_id}</dd></div>
                    <div><dt>منبع داده</dt><dd>{sourceLabel(evse.source_code)}</dd></div>
                    <div><dt>نوع وضعیت</dt><dd>{evse.status_kind === "operational" ? "عملیاتی، نه زنده" : "وضعیت زنده"}</dd></div>
                    {evse.reported_status_label && evse.reported_status !== evse.status && (
                      <div><dt>وضعیت خام منبع</dt><dd>{evse.reported_status_label}</dd></div>
                    )}
                  </dl>
                </details>
                */}
              </article>
            ))}
          </section>
        </div>
      )}
    </aside>
  );
}
