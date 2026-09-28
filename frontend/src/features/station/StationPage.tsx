import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import L from "leaflet";
import { MapContainer, Marker, TileLayer } from "react-leaflet";
import { ApiError, fetchLocationBySlug, fetchNearbyLocations } from "../../api/client";
import type { LocationDetail } from "../../api/types";
import { EMPTY_FILTERS } from "../../lib/filters";
import { formatNumber, formatOperatorName, formatPower, operatorLabelOrNull } from "../../lib/format";
import { stationHref } from "../../lib/station";
import { ConnectorMark } from "../../ui/ConnectorMark";
import { IconBolt, IconOperator, IconPin, IconPlug } from "../../ui/icons";
import logo from "../../assets/ev98-logo.png";
import "./station.css";

const SITE = "https://ev98.ir";

const pinIcon = L.divIcon({
  className: "station-pin",
  html: '<img src="/map-pins/station-operational.svg" alt="" width="44" height="56" />',
  iconSize: [44, 56],
  iconAnchor: [22, 56],
});

function setHead(selector: string, value: string) {
  const el = document.head.querySelector(selector);
  if (!el) return;
  el.setAttribute(el.hasAttribute("content") ? "content" : "href", value);
}

function useStationMeta(slug: string, location: LocationDetail | undefined, missing: boolean) {
  const summary = location ? stationSummary(location) : "";
  useEffect(() => {
    const previousTitle = document.title;
    const snapshots = [...document.head.querySelectorAll("meta[name], meta[property], link[rel='canonical']")].map((el) => ({
      el,
      content: el.getAttribute("content"),
      href: el.getAttribute("href"),
    }));
    const restore = () => {
      document.title = previousTitle;
      for (const snap of snapshots) {
        if (snap.content != null) snap.el.setAttribute("content", snap.content);
        if (snap.href != null) snap.el.setAttribute("href", snap.href);
      }
      document.getElementById("station-jsonld")?.remove();
    };

    if (missing) {
      document.title = "ایستگاه پیدا نشد | EV98";
      setHead('meta[name="robots"]', "noindex, follow");
      return restore;
    }
    if (!location) {
      document.title = "ایستگاه شارژ | EV98";
      return restore;
    }

    const place = location.city ? ` در ${location.city}` : "";
    const url = `${SITE}${stationHref(location.slug || slug)}`;
    document.title = `${location.name}${place} | EV98`;
    setHead('meta[name="description"]', summary);
    setHead('meta[name="robots"]', "index, follow");
    setHead('link[rel="canonical"]', url);
    setHead('meta[property="og:title"]', document.title);
    setHead('meta[property="og:description"]', summary);
    setHead('meta[property="og:url"]', url);
    setHead('meta[name="twitter:title"]', document.title);
    setHead('meta[name="twitter:description"]', summary);
    if (location.images[0]) {
      setHead('meta[property="og:image"]', location.images[0]);
      setHead('meta[name="twitter:image"]', location.images[0]);
    }

    const data = {
      "@context": "https://schema.org",
      "@type": "Place",
      name: location.name,
      description: summary,
      url,
      telephone: location.phone || undefined,
      image: location.images[0],
      address: {
        "@type": "PostalAddress",
        streetAddress: location.address || undefined,
        addressLocality: location.city || undefined,
        addressRegion: location.province || undefined,
        addressCountry: "IR",
      },
      geo: {
        "@type": "GeoCoordinates",
        latitude: location.lat,
        longitude: location.lng,
      },
    };
    document.getElementById("station-jsonld")?.remove();
    const script = document.createElement("script");
    script.id = "station-jsonld";
    script.type = "application/ld+json";
    script.textContent = JSON.stringify(data);
    document.head.appendChild(script);
    return restore;
  }, [location, missing, slug, summary]);
}

function stationSummary(location: LocationDetail): string {
  const operator = operatorLabelOrNull(location.operator_name);
  const place = [location.city, location.province].filter(Boolean).join("، ");
  const plugs = plugList(location).map((plug) => plug.label);
  const name = location.name.replace(/^ایستگاه\s+شارژ\s+/, "");
  const parts = [
    `ایستگاه شارژ ${name}`,
    place ? `در ${place}` : null,
    operator ? `اپراتور ${operator}` : null,
    location.max_power_kw != null ? `حداکثر توان ${formatPower(location.max_power_kw)}` : null,
    plugs.length > 0 ? `کانکتور ${plugs.join("، ")}` : null,
    location.hours_label || location.hours_summary,
  ].filter(Boolean);
  return `${parts.join("، ")}.`;
}

function plugList(location: LocationDetail) {
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

function connectorCount(location: LocationDetail): number {
  return location.evses.reduce((total, evse) => total + (evse.counts?.total ?? evse.connectors.length), 0);
}

function powerTypeLabel(value: string | null): string {
  if (!value) return "نوع جریان نامشخص";
  const normalized = value.toUpperCase();
  if (normalized.includes("DC")) return "شارژ سریع DC";
  if (normalized.includes("AC")) return "شارژ AC";
  return value.replaceAll("_", " ");
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

function formatDistance(meters: number): string {
  if (meters < 1000) return `${formatNumber(Math.round(meters))} متر`;
  return `${formatNumber(Math.round(meters / 100) / 10)} کیلومتر`;
}

function accessLabel(location: LocationDetail): string {
  if (location.is_public === false) return "غیرعمومی";
  if (location.is_public === true) return "عمومی";
  return "دسترسی نامشخص";
}

function hoursLabel(location: LocationDetail): string {
  if (location.is_24_7) return "شبانه‌روزی";
  return location.hours_label || location.hours_summary || "ساعت ثبت نشده";
}

function StationGallery({ images, name }: { images: string[]; name: string }) {
  const [index, setIndex] = useState(0);
  const [failed, setFailed] = useState<Set<string>>(() => new Set());
  const visible = images.filter((image) => !failed.has(image));
  if (visible.length === 0) return null;
  const current = visible[Math.min(index, visible.length - 1)];
  return (
    <figure>
      <div className="station-photo">
        <img
          src={current}
          alt={`نمای ${name}`}
          width={960}
          height={540}
          decoding="async"
          onError={() => setFailed((items) => new Set(items).add(current))}
        />
      </div>
      {visible.length > 1 && (
        <div className="station-thumbs" role="group" aria-label="تصاویر ایستگاه">
          {visible.map((image, imageIndex) => (
            <button
              key={image}
              type="button"
              aria-label={`تصویر ${formatNumber(imageIndex + 1)}`}
              aria-pressed={image === current}
              onClick={() => setIndex(imageIndex)}
            >
              <img src={image} alt="" />
            </button>
          ))}
        </div>
      )}
    </figure>
  );
}

function StationMap({ lat, lng, name }: { lat: number; lng: number; name: string }) {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return (
    <div className="station-map-frame" role="img" aria-label={`موقعیت ${name} روی نقشه`}>
      <MapContainer
        center={[lat, lng]}
        zoom={16}
        zoomControl={false}
        dragging={false}
        scrollWheelZoom={false}
        doubleClickZoom={false}
        touchZoom={false}
        boxZoom={false}
        keyboard={false}
        zoomAnimation={!reducedMotion}
        attributionControl
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Marker position={[lat, lng]} icon={pinIcon} />
      </MapContainer>
    </div>
  );
}

export default function StationPage({ slug }: { slug: string }) {
  const detail = useQuery({
    queryKey: ["station-page", slug],
    queryFn: () => fetchLocationBySlug(slug),
  });
  const location = detail.data;
  const missing = detail.error instanceof ApiError && detail.error.status === 404;
  useStationMeta(slug, location, missing);

  const nearby = useQuery({
    queryKey: ["station-nearby", location?.id],
    queryFn: () => fetchNearbyLocations(location!.lat, location!.lng, EMPTY_FILTERS, 30_000, 7),
    enabled: Boolean(location),
  });
  const neighbors = useMemo(
    () => (nearby.data?.items ?? []).filter((item) => item.slug && item.id !== location?.id).slice(0, 4),
    [location?.id, nearby.data?.items],
  );

  useEffect(() => {
    if (detail.isLoading) return;
    document.getElementById("station-main")?.focus({ preventScroll: true });
  }, [detail.isLoading, slug]);

  const plugs = location ? plugList(location) : [];
  const site = location ? safeHttp(location.website) : null;
  const operator = location ? operatorLabelOrNull(location.operator_name) : null;
  const summary = location ? stationSummary(location) : "";

  return (
    <div className="station-page">
      <a className="skip" href="#station-main">
        رفتن به محتوای ایستگاه
      </a>
      <header className="station-header">
        <div className="station-header-inner">
          <a className="station-logo" href="/" aria-label="EV98، بازگشت به نقشه">
            <img src={logo} alt="EV98" />
          </a>
          <a className="station-map-link" href="/">
            <IconPin />
            نقشه
          </a>
        </div>
      </header>

      {detail.isLoading && (
        <section className="station-hero" aria-busy="true">
          <div className="station-hero-inner station-skeleton" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <p className="visually-hidden">در حال دریافت ایستگاه</p>
        </section>
      )}

      {detail.error && (
        <main id="station-main" className="station-main" tabIndex={-1}>
          <div className="station-status">
            <h1>{missing ? "این ایستگاه پیدا نشد" : "جزئیات ایستگاه دریافت نشد"}</h1>
            <p>{missing ? "آدرس درست است، ولی این ایستگاه در فهرست EV98 نیست." : "اتصال برقرار نشد. دوباره تلاش کنید."}</p>
            <a className="station-map-link" href="/">
              بازگشت به نقشه
            </a>
            {!missing && (
              <button type="button" className="station-retry" onClick={() => void detail.refetch()}>
                تلاش دوباره
              </button>
            )}
          </div>
        </main>
      )}

      {location && (
        <>
          <section className="station-hero">
            <div className="station-hero-inner">
              <p className="station-crumb">
                <a href="/">نقشه شارژ</a>
                <span aria-hidden="true">/</span>
                <span aria-current="page">{location.city || location.province || "ایران"}</span>
              </p>
              <div className="station-hero-layout">
                <div className="station-hero-copy">
                  <div className="station-status-row">
                    {location.open_now_label && (
                      <span className={`station-live-status${location.open_now === false ? " is-closed" : ""}`}>
                        <i aria-hidden="true" />
                        {location.open_now_label}
                      </span>
                    )}
                    <span className="station-availability">
                      {location.is_stale ? "وضعیت لحظه‌ای تأیید نشده" : location.availability_label}
                    </span>
                  </div>
                  <h1>{location.name}</h1>
                  <p className="station-hero-address">
                    {location.address || [location.city, location.province].filter(Boolean).join("، ") || "آدرس ثبت نشده"}
                  </p>
                  <p className="station-kicker">
                    {operator && (
                      <span>
                        <IconOperator />
                        اپراتور {formatOperatorName(location.operator_name)}
                      </span>
                    )}
                    <span>
                      <IconPlug />
                      {connectorCount(location) > 0 ? `${formatNumber(connectorCount(location))} کانکتور` : "کانکتور ثبت نشده"}
                    </span>
                  </p>
                </div>
                <aside className="station-hero-panel" aria-label="اقدام‌های ایستگاه">
                  <span className="station-panel-label">آماده حرکت هستید؟</span>
                  <strong>{formatPower(location.max_power_kw)}</strong>
                  <span>{hoursLabel(location)}</span>
                  <div className="station-actions">
                    <a
                      className="station-cta is-primary"
                      href={`https://www.google.com/maps/dir/?api=1&destination=${location.lat},${location.lng}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <IconPin />
                      مسیریابی
                    </a>
                    <a className="station-cta is-secondary" href={`/?location=${location.id}`}>
                      نمایش روی نقشه
                    </a>
                  </div>
                </aside>
              </div>
            </div>
          </section>

          <main id="station-main" className="station-main" tabIndex={-1}>
            <section className="station-overview" aria-label="خلاصه ایستگاه">
              <p className="station-lead">{summary}</p>
              <dl className="station-facts">
              <div>
                <IconBolt />
                <dt>توان</dt>
                <dd>{formatPower(location.max_power_kw)}</dd>
              </div>
              <div>
                <IconPlug />
                <dt>کانکتور</dt>
                <dd>{connectorCount(location) > 0 ? formatNumber(connectorCount(location)) : "ثبت نشده"}</dd>
              </div>
              <div>
                <dt>ساعت کار</dt>
                <dd>{hoursLabel(location)}</dd>
              </div>
              <div>
                <dt>دسترسی</dt>
                <dd>{accessLabel(location)}</dd>
              </div>
              </dl>
            </section>

            <section className="station-location" aria-labelledby="station-place-title">
              <div className="station-location-copy">
                <span className="station-section-index" aria-hidden="true">موقعیت</span>
                <h2 id="station-place-title">مسیر رسیدن به ایستگاه</h2>
                <p className="station-address">
                  {location.address || [location.city, location.province].filter(Boolean).join("، ") || "آدرس ثبت نشده"}
                </p>
                <p className="station-coords" dir="ltr">
                  {location.lat.toFixed(5)}, {location.lng.toFixed(5)}
                </p>
                {plugs.length > 0 && (
                  <div className="station-plugs">
                    {plugs.map((plug) => (
                      <span key={plug.key}>
                        <ConnectorMark standard={plug.standard} format={plug.format} />
                        {plug.label}
                      </span>
                    ))}
                  </div>
                )}
                {(site || location.phone || location.price) && (
                  <div className="station-links">
                    {location.phone && (
                      <a href={`tel:${location.phone}`} dir="ltr">
                        {location.phone}
                      </a>
                    )}
                    {site && (
                      <a href={site} target="_blank" rel="noreferrer">
                        وب‌سایت ایستگاه
                      </a>
                    )}
                    {location.price && (
                      <span className="station-chip">
                        {location.price.is_free
                          ? "رایگان"
                          : `${formatNumber(location.price.amount_toman)} تومان / کیلووات‌ساعت`}
                      </span>
                    )}
                  </div>
                )}
                {location.facilities.length > 0 && (
                  <div className="station-facilities" aria-label="امکانات اطراف">
                    {location.facilities.map((item) => (
                      <span key={item}>{item}</span>
                    ))}
                  </div>
                )}
              </div>
              <StationMap lat={location.lat} lng={location.lng} name={location.name} />
            </section>

            {(location.images.length > 0 || location.notes.length > 0) && (
              <section className="station-card station-media-card" aria-labelledby="station-notes-title">
                <h2 id="station-notes-title">{location.images.length > 0 ? "تصویر و توضیح" : "توضیح"}</h2>
                <StationGallery images={location.images} name={location.name} />
                {location.notes.map((note) => (
                  <p key={`${note.kind}-${note.text}`}>{note.text}</p>
                ))}
              </section>
            )}

            <section className="station-card station-gear-card" aria-labelledby="station-gear-title">
              <div className="station-section-head">
                <div>
                  <span className="station-section-index" aria-hidden="true">جزئیات فنی</span>
                  <h2 id="station-gear-title">شارژرهای این ایستگاه</h2>
                </div>
              {location.evses.length === 0 && <p>تجهیزی برای این ایستگاه ثبت نشده.</p>}
              {location.evses.length > 0 && (
                  <p className="station-section-count">
                  {formatNumber(location.evses.length)} دستگاه، {formatNumber(connectorCount(location))} کانکتور
                </p>
              )}
              </div>
              <div className="station-evse-list">
              {location.evses.map((evse, index) => (
                <article key={evse.id} className="station-evse">
                  <header>
                    <div>
                      <strong>شارژر {formatNumber(index + 1)}</strong>
                      <p>{formatPower(evse.max_power_kw)}</p>
                    </div>
                  </header>
                  <ul>
                    {evse.connectors.map((connector) => (
                      <li key={connector.id}>
                        <ConnectorMark standard={connector.standard} format={connector.format} />
                        <span>
                          <b>{connector.standard_label}</b>
                          <small>
                            {powerTypeLabel(connector.power_type)} · {formatPower(connector.max_power_kw)}
                          </small>
                        </span>
                      </li>
                    ))}
                  </ul>
                  {evse.connectors.length === 0 && <p>جزئیات اتصال این دستگاه ثبت نشده.</p>}
                </article>
              ))}
              </div>
            </section>

            {neighbors.length > 0 && (
              <section className="station-card station-nearby-card" aria-labelledby="station-nearby-title">
                <div className="station-section-head">
                  <div>
                    <span className="station-section-index" aria-hidden="true">انتخاب‌های دیگر</span>
                    <h2 id="station-nearby-title">ایستگاه‌های نزدیک</h2>
                  </div>
                  <a className="station-all-link" href="/">دیدن روی نقشه</a>
                </div>
                <ul className="station-nearby">
                  {neighbors.map((item) => (
                    <li key={item.id}>
                      <a href={stationHref(item.slug!)}>
                        <strong>{item.name}</strong>
                        <small>
                          {[item.city, formatPower(item.max_power_kw), item.distance_m != null ? formatDistance(item.distance_m) : null]
                            .filter(Boolean)
                            .join(" · ")}
                        </small>
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </main>
          <footer className="station-footer">
            <a href="/">EV98</a>
            <span> · </span>
            <a href="/cars/">خودروهای برقی وارداتی</a>
          </footer>
        </>
      )}
    </div>
  );
}
