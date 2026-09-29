import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { ApiError, planTrip, reverseTripPlace, searchTripPlaces } from "../../api/client";
import type { PlaceSuggestion, TripPlan, VehicleVariant } from "../../api/types";
import { useVehicleCatalog, variantMatches } from "../../lib/vehicles";
import { readMapState } from "../../lib/filters";
import logo from "../../assets/ev98-logo.webp";
import { cacheTrip, readCachedTrip } from "./tripCache";
import { readTripUrl, tripUrl } from "./tripUrl";
import "./trip.css";

function decodePolyline(encoded: string): [number, number][] {
  const points: [number, number][] = [];
  let lat = 0, lng = 0, index = 0;
  while (index < encoded.length) {
    const values: number[] = [];
    for (let coordinate = 0; coordinate < 2; coordinate++) {
      let shift = 0, result = 0, code: number;
      do {
        code = encoded.charCodeAt(index++) - 63;
        result |= (code & 31) << shift;
        shift += 5;
      } while (code >= 32 && index < encoded.length);
      values.push((result >> 1) ^ -(result & 1));
    }
    lat += values[0]; lng += values[1];
    points.push([lat / 1e5, lng / 1e5]);
  }
  return points;
}

function FitRoute({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length > 1) map.fitBounds(points, { padding: [34, 34] });
  }, [map, points]);
  return null;
}

function FitSelectedPoints({ origin, destination, hasRoute }: { origin: PlaceSuggestion | null; destination: PlaceSuggestion | null; hasRoute: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (hasRoute) return;
    if (origin && destination) map.fitBounds([[origin.lat, origin.lng], [destination.lat, destination.lng]], { padding: [48, 48], maxZoom: 13 });
    else if (origin || destination) map.panTo([origin?.lat ?? destination!.lat, origin?.lng ?? destination!.lng]);
  }, [map, origin, destination, hasRoute]);
  return null;
}

type PickTarget = "origin" | "destination";

function PlaceField({ label, value, onChange, picking, onPick }: {
  label: string;
  value: PlaceSuggestion | null;
  onChange: (value: PlaceSuggestion | null) => void;
  picking: boolean;
  onPick: () => void;
}) {
  const inputId = useId();
  const [text, setText] = useState(value?.title ?? "");
  const [items, setItems] = useState<PlaceSuggestion[]>([]);
  const [showAlternatives, setShowAlternatives] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const searchRequest = useRef(0);
  useEffect(() => {
    if (value) {
      searchRequest.current += 1;
      setBusy(false);
      setText(value.title);
    }
  }, [value]);
  async function runSearch() {
    const query = text.trim();
    if (query.length < 3) return;
    const request = ++searchRequest.current;
    setBusy(true);
    setError("");
    setItems([]);
    setShowAlternatives(false);
    try {
      const results = await searchTripPlaces(query);
      if (request !== searchRequest.current) return;
      if (!results.length) { setError("مکانی پیدا نشد. آدرس دقیق‌تری وارد کنید."); return; }
      onChange(results[0]);
      setText(results[0].title);
      setItems(results.length > 1 ? results : []);
    } catch (cause) {
      if (request === searchRequest.current) setError(cause instanceof ApiError ? cause.message : "جست‌وجو انجام نشد.");
    } finally {
      if (request === searchRequest.current) setBusy(false);
    }
  }
  return <div className="trip-field trip-place-field">
    <div className="trip-field-labelrow"><label htmlFor={inputId}>{label}<span className="trip-required"> *</span></label><button type="button" className="trip-pick-button" aria-pressed={picking} onClick={onPick}>{picking ? "روی نقشه انتخاب کن" : "انتخاب روی نقشه"}</button></div>
    <div className="trip-place-control"><input id={inputId} value={text} autoComplete="off" placeholder="نام شهر، خیابان یا مکان" onChange={(event) => { searchRequest.current += 1; setBusy(false); setText(event.target.value); onChange(null); setItems([]); setShowAlternatives(false); setError(""); }} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void runSearch(); } }} /><button type="button" disabled={busy || text.trim().length < 3} onClick={() => void runSearch()}>جست‌وجو</button></div>
    {busy && <span className="trip-field-hint" role="status">در حال جست‌وجو…</span>}
    {error && <span className="trip-field-error" role="alert">{error}</span>}
    {items.length > 1 && <><button type="button" className="trip-alternative-toggle" onClick={() => setShowAlternatives((current) => !current)}>{showAlternatives ? "بستن نتایج" : "نتیجهٔ اول انتخاب شد؛ تغییر مکان"}</button>{showAlternatives && <ul className="trip-suggestions">
      {items.map((item, index) => <li key={`${item.lat}-${item.lng}-${index}`}><button type="button" aria-pressed={value?.lat === item.lat && value?.lng === item.lng} onClick={() => { onChange(item); setText(item.title); setItems([]); setShowAlternatives(false); }}>
        <strong>{item.title}</strong><small>{item.address}</small>
      </button></li>)}
    </ul>}</>}
    {value && <span className="trip-field-hint">موقعیت انتخاب شد</span>}
  </div>;
}

function VehicleField({ value, onChange, vehicles }: { value: VehicleVariant | null; onChange: (value: VehicleVariant) => void; vehicles: VehicleVariant[] }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const matches = useMemo(() => vehicles.filter((item) => variantMatches(item.search, query)).slice(0, 50), [vehicles, query]);
  return <div className="trip-field trip-place-field">
    <label htmlFor="trip-vehicle">خودرو<span className="trip-required"> *</span></label>
    <input id="trip-vehicle" value={open ? query : value?.display_name ?? query} placeholder="مدل خودرو را جست‌وجو کنید" autoComplete="off" onFocus={() => { setOpen(true); setQuery(""); }} onChange={(event) => { setQuery(event.target.value); setOpen(true); }} />
    {open && <ul className="trip-suggestions trip-vehicle-options">
      {matches.map((item) => <li key={item.id}><button type="button" onClick={() => { onChange(item); setOpen(false); setQuery(""); }}><strong>{item.display_name}</strong><small>{item.range_km ? `برد ثبت‌شده ${Math.round(item.range_km)} کیلومتر` : "برد ثبت نشده"}</small></button></li>)}
      {matches.length === 0 && <li className="trip-no-result">خودرویی پیدا نشد</li>}
    </ul>}
    {value && !open && <span className="trip-field-hint">{value.station_standards.length} نوع سوکت سازگار</span>}
  </div>;
}

function ClickToPick({ picking, onPick }: { picking: PickTarget | null; onPick: (lat: number, lng: number) => void }) {
  useMapEvents({ click(event) { if (picking) onPick(event.latlng.lat, event.latlng.lng); } });
  return null;
}

function TripMap({ plan, origin, destination, picking, onPick }: { plan: TripPlan | null; origin: PlaceSuggestion | null; destination: PlaceSuggestion | null; picking: PickTarget | null; onPick: (lat: number, lng: number) => void }) {
  const points = useMemo(() => plan?.polyline ? decodePolyline(plan.polyline) : [], [plan?.polyline]);
  return <div className={`trip-map${picking ? " is-picking" : ""}`} aria-label="نقشه انتخاب مبدأ و مقصد">
    {picking && <div className="trip-map-hint" role="status">برای ثبت {picking === "origin" ? "مبدأ" : "مقصد"} روی نقشه کلیک کن</div>}
    <MapContainer center={[32.4, 53.7]} zoom={5} scrollWheelZoom={false}>
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <ClickToPick picking={picking} onPick={onPick} />
      <FitRoute points={points} />
      <FitSelectedPoints origin={origin} destination={destination} hasRoute={points.length > 1} />
      {points.length > 1 && <Polyline positions={points} pathOptions={{ color: "#087a65", weight: 6, opacity: 0.9 }} />}
      {origin && <CircleMarker center={[origin.lat, origin.lng]} radius={9} pathOptions={{ color: "#065a4b", fillColor: "#ffffff", fillOpacity: 1, weight: 4 }}><Tooltip permanent direction="top">مبدأ</Tooltip></CircleMarker>}
      {destination && <CircleMarker center={[destination.lat, destination.lng]} radius={9} pathOptions={{ color: "#102a27", fillColor: "#ffffff", fillOpacity: 1, weight: 4 }}><Tooltip permanent direction="top">مقصد</Tooltip></CircleMarker>}
      {plan?.stops.map((stop, index) => <CircleMarker key={stop.id} center={[stop.lat, stop.lng]} radius={10} pathOptions={{ color: "#b86e1b", fillColor: "#ffffff", fillOpacity: 1, weight: 4 }}><Tooltip>{index + 1}. {stop.name}</Tooltip></CircleMarker>)}
    </MapContainer>
  </div>;
}

function formatKm(meters: number) { return `${Math.round(meters / 1000).toLocaleString("fa-IR")} کیلومتر`; }
function formatTime(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return `${hours ? `${hours.toLocaleString("fa-IR")} ساعت و ` : ""}${minutes.toLocaleString("fa-IR")} دقیقه`;
}

export default function TripPage() {
  const [initialTrip] = useState(readTripUrl);
  const catalog = useVehicleCatalog();
  const vehicles = useMemo(() => catalog.data?.makes.flatMap((make) => make.models.flatMap((model) => model.variants)).filter((item) => (item.powertrain_type === "BEV" || item.powertrain_type === "PHEV") && item.range_km && item.station_standards.length) ?? [], [catalog.data]);
  const [origin, setOrigin] = useState<PlaceSuggestion | null>(initialTrip.origin);
  const [destination, setDestination] = useState<PlaceSuggestion | null>(initialTrip.destination);
  const [vehicleId, setVehicleId] = useState<string | null>(() => initialTrip.vehicleId ?? readMapState().filters.vehicleId);
  const vehicle = useMemo(() => vehicles.find((item) => item.id === vehicleId) ?? null, [vehicles, vehicleId]);
  const [soc, setSoc] = useState(initialTrip.soc);
  const [plan, setPlan] = useState<TripPlan | null>(null);
  const [plannedPoints, setPlannedPoints] = useState<{ origin: PlaceSuggestion; destination: PlaceSuggestion } | null>(null);
  const [picking, setPicking] = useState<PickTarget | null>(initialTrip.origin ? initialTrip.destination ? null : "destination" : "origin");
  const mapPanelRef = useRef<HTMLDivElement | null>(null);
  const planRequest = useRef(0);
  const restoredPlanStarted = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [shareStatus, setShareStatus] = useState("");
  useEffect(() => { document.title = "برنامه‌ریزی سفر برقی | EV98"; }, []);
  useEffect(() => {
    const next = tripUrl(window.location.href, { origin, destination, vehicleId, soc });
    if (next.href !== window.location.href) window.history.replaceState(window.history.state, "", next);
  }, [origin, destination, vehicleId, soc]);
  useEffect(() => {
    if (restoredPlanStarted.current || !initialTrip.origin || !initialTrip.destination || !initialTrip.vehicleId || !vehicle || vehicle.id !== initialTrip.vehicleId) return;
    if (origin?.lat !== initialTrip.origin.lat || origin?.lng !== initialTrip.origin.lng || destination?.lat !== initialTrip.destination.lat || destination?.lng !== initialTrip.destination.lng || soc !== initialTrip.soc) return;
    restoredPlanStarted.current = true;
    const cached = readCachedTrip(initialTrip.origin, initialTrip.destination, vehicle.id, initialTrip.soc);
    if (cached) { setPlan(cached); setPlannedPoints({ origin: initialTrip.origin, destination: initialTrip.destination }); return; }
    void calculateTrip(initialTrip.origin, initialTrip.destination, vehicle, initialTrip.soc);
  }, [vehicle, origin, destination, soc]);
  function changePlace(target: PickTarget, place: PlaceSuggestion | null) {
    planRequest.current += 1;
    setBusy(false);
    if (target === "origin") setOrigin(place);
    else setDestination(place);
    setPlan(null);
    setPlannedPoints(null);
    setError("");
    setShareStatus("");
    if (!place) setPicking(target);
    else if (target === "origin" && !destination) setPicking("destination");
    else setPicking(null);
  }
  function beginPick(target: PickTarget) {
    setPicking(target);
    mapPanelRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  }
  function pickFromMap(lat: number, lng: number) {
    const target = picking;
    if (!target) return;
    const fallback = { title: "نقطهٔ انتخاب‌شده روی نقشه", address: `${lat.toFixed(5)}, ${lng.toFixed(5)}`, lat, lng };
    changePlace(target, fallback);
    void reverseTripPlace(lat, lng).then((place) => {
      const update = (current: PlaceSuggestion | null) => current?.lat === lat && current?.lng === lng ? place : current;
      if (target === "origin") setOrigin(update);
      else setDestination(update);
    }).catch(() => { /* Exact coordinates remain usable when reverse geocoding is unavailable. */ });
  }
  async function calculateTrip(start: PlaceSuggestion, end: PlaceSuggestion, car: VehicleVariant, charge: number) {
    const request = ++planRequest.current;
    setBusy(true); setError(""); setPlan(null);
    try {
      const result = await planTrip({ origin_lat: start.lat, origin_lng: start.lng, destination_lat: end.lat, destination_lng: end.lng, vehicle_id: car.id, start_soc: charge });
      if (request === planRequest.current) { cacheTrip(start, end, car.id, charge, result); setPlan(result); setPlannedPoints({ origin: start, destination: end }); }
    } catch (cause) {
      if (request === planRequest.current) setError(cause instanceof ApiError ? cause.message : "برنامه‌ریزی سفر انجام نشد.");
    } finally { if (request === planRequest.current) setBusy(false); }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!origin) { setError("مبدأ را جست‌وجو کنید یا روی نقشه انتخاب کنید."); return; }
    if (!destination) { setError("مقصد را جست‌وجو کنید یا روی نقشه انتخاب کنید."); return; }
    if (!vehicle) { setError("خودرو را از فهرست انتخاب کنید."); return; }
    if (!vehicle.range_km || !vehicle.station_standards.length) { setError("دادهٔ برد یا سوکت این خودرو برای برنامه‌ریزی کامل نیست."); return; }
    void calculateTrip(origin, destination, vehicle, soc);
  }
  async function copyTripLink() {
    if (!origin || !destination) return;
    const link = tripUrl(window.location.href, { origin, destination, vehicleId, soc }).href;
    try {
      await navigator.clipboard.writeText(link);
      setShareStatus("لینک سفر کپی شد.");
    } catch {
      setShareStatus("کپی خودکار ممکن نشد؛ لینک را از نوار آدرس بردارید.");
    }
  }
  return <div className="trip-page" dir="rtl">
    <a className="skip" href="#trip-form">رفتن به فرم برنامه‌ریزی</a>
    <header className="trip-header"><a href="/" aria-label="بازگشت به صفحه اصلی EV98"><img src={logo} alt="EV98" /></a><nav><a href="/">نقشه ایستگاه‌ها</a><a href="/cars/">خودروها</a></nav></header>
    <main className="trip-container">
      <div className="trip-heading"><span className="trip-eyebrow">EV98 / برنامه‌ریز سفر</span><h1>مسیرت را با خیال راحت شارژ کن</h1><p>مبدأ، مقصد و خودرو را انتخاب کن تا توقف‌های شارژ سازگار در مسیر پیدا شوند.</p></div>
      <div className="trip-layout">
        <section className="trip-card trip-form-card" id="trip-form" aria-label="مشخصات سفر">
          <div className="trip-card-heading"><span className="trip-step">۰۱</span><div><h2>مشخصات سفر</h2><p>مکان‌ها را جست‌وجو کن یا روی نقشه انتخاب کن.</p></div></div>
          <form onSubmit={submit}>
            <PlaceField label="مبدأ" value={origin} onChange={(place) => changePlace("origin", place)} picking={picking === "origin"} onPick={() => beginPick("origin")} />
            <PlaceField label="مقصد" value={destination} onChange={(place) => changePlace("destination", place)} picking={picking === "destination"} onPick={() => beginPick("destination")} />
            <VehicleField value={vehicle} onChange={(item) => { planRequest.current += 1; setVehicleId(item.id); setPlan(null); setPlannedPoints(null); setBusy(false); setShareStatus(""); }} vehicles={vehicles} />
            <div className="trip-field"><label htmlFor="trip-soc">شارژ فعلی باتری</label><div className="trip-soc-control"><input id="trip-soc" type="range" min="1" max="100" value={soc} onChange={(event) => { planRequest.current += 1; setSoc(Number(event.target.value)); setPlan(null); setPlannedPoints(null); setBusy(false); setShareStatus(""); }} /><output htmlFor="trip-soc">{soc.toLocaleString("fa-IR")}٪</output></div></div>
            <p className="trip-assumption">برای احتیاط، برد عملی خودرو ۷۵٪ برد ثبت‌شده و حداقل شارژ هنگام رسیدن ۱۰٪ در نظر گرفته می‌شود.</p>
            {error && <p className="trip-error" role="alert">{error}</p>}
            <button className="trip-submit" type="submit" disabled={busy || catalog.isLoading}>{busy ? "در حال بررسی مسیر…" : "پیدا کردن توقف‌های شارژ"}</button>
            {origin && destination && <button className="trip-share" type="button" onClick={() => void copyTripLink()}>کپی لینک سفر</button>}
            {shareStatus && <p className="trip-field-hint" role="status">{shareStatus}</p>}
          </form>
        </section>
        <section className="trip-card trip-results" aria-live="polite" aria-label="نتیجه برنامه‌ریزی سفر">
          <div className="trip-result-heading"><span className="trip-step">۰۲ / {plan ? "نتیجه مسیر" : origin && destination ? "آمادهٔ بررسی" : "انتخاب مکان"}</span><h2>{busy ? "در حال محاسبه مسیر" : plan ? plan.status === "ok" ? plan.stops.length ? `${plan.stops.length.toLocaleString("fa-IR")} توقف شارژ در مسیر` : "بدون توقف شارژ می‌رسی" : "مسیر قابل‌اطمینان پیدا نشد" : origin && destination ? "مبدأ و مقصد آماده‌اند" : "مبدأ و مقصد را مشخص کن"}</h2><p>{busy ? "فاصلهٔ جاده‌ای و ایستگاه‌های سازگار بررسی می‌شوند…" : plan && plannedPoints ? `${plannedPoints.origin.title} ← ${plannedPoints.destination.title}` : origin && destination ? `${origin.title} ← ${destination.title}` : "مکان‌ها را جست‌وجو کن یا روی نقشه انتخاب کن."}</p></div>
          <div ref={mapPanelRef}><TripMap plan={plan} origin={origin} destination={destination} picking={picking} onPick={pickFromMap} /></div>
          {!plan && !busy && <p className="trip-map-caption">پس از انتخاب دو نقطه و خودرو، توقف‌های شارژ سازگار در همین‌جا نمایش داده می‌شوند.</p>}
          {plan && plannedPoints && <>
            {plan.status === "ok" && plan.stops.length > 0 && !plan.route_includes_stops && <p className="trip-map-note">خط نقشه مسیر کلی سفر است؛ فاصلهٔ جاده‌ای تا ایستگاه‌ها جداگانه محاسبه شده است.</p>}
            {plan.status === "ok" ? <>
              <div className="trip-stats"><div><small>طول مسیر</small><strong>{formatKm(plan.total_distance_m ?? 0)}</strong></div><div><small>زمان رانندگی</small><strong>{formatTime(plan.total_duration_s ?? 0)}</strong></div><div><small>توقف و شارژ</small><strong>{plan.total_stop_duration_s != null ? formatTime(plan.total_stop_duration_s) : "نامشخص"}</strong></div><div className="trip-total-time"><small>زمان کل سفر</small><strong>{plan.total_trip_duration_s != null ? formatTime(plan.total_trip_duration_s) : "نامشخص"}</strong></div><div><small>شارژ هنگام رسیدن</small><strong>{plan.arrival_soc?.toLocaleString("fa-IR")}٪</strong></div></div>
              <ol className="trip-timeline"><li><span className="trip-timeline-dot" /><div><strong>حرکت از {plannedPoints.origin.title}</strong><small>شارژ شروع: {soc.toLocaleString("fa-IR")}٪</small></div></li>
                {plan.stops.map((stop, index) => <li key={stop.id}><span className="trip-timeline-dot is-charge" /><div><strong><a href={`/stations/${stop.slug}`}>{stop.name}</a></strong><small>بعد از {formatKm(plan.legs[index].distance_m)} · شارژ ورود {stop.arrival_soc.toLocaleString("fa-IR")}٪ → خروج {stop.departure_soc.toLocaleString("fa-IR")}٪</small><small>{stop.stop_duration_s != null ? `حدود ${formatTime(stop.charging_duration_s ?? 0)} شارژ + ۵ دقیقه آماده‌سازی = ${formatTime(stop.stop_duration_s)} توقف` : "زمان توقف قابل تخمین نیست"}{stop.charge_added_kwh != null ? ` · ${stop.charge_added_kwh.toLocaleString("fa-IR", { maximumFractionDigits: 1 })} کیلووات‌ساعت` : ""}</small><small>{stop.charging_power_kw ? `توان مبنای تخمین ${stop.charging_power_kw.toLocaleString("fa-IR")} کیلووات${stop.charging_power_assumed ? " (فرضی)" : ""}` : "توان شارژ ثبت نشده"} · {stop.availability === "available" ? "شارژر آزاد گزارش شده؛ پیش از حرکت بررسی کن" : "وضعیت لحظه‌ای نامشخص است"}</small></div></li>)}
                <li><span className="trip-timeline-dot is-end" /><div><strong>رسیدن به {plannedPoints.destination.title}</strong><small>شارژ باقی‌ماندهٔ تخمینی: {plan.arrival_soc?.toLocaleString("fa-IR")}٪</small></div></li></ol>
            </> : <p className="trip-error">{plan.reason}</p>}
            <p className="trip-caution">زمان شارژ با میانگین ۷۵٪ توان مبنا و ۵ دقیقه آماده‌سازی برای هر توقف تخمین زده شده است. وقتی سقف توان شارژ خودرو ثبت نشده باشد، سقف ۸۰ کیلووات DC یا ۱۱ کیلووات AC فرض می‌شود؛ برای توان نامشخص سوکت هم ۵۰ کیلووات DC یا ۷ کیلووات AC در نظر گرفته می‌شود. صف انتظار و منحنی شارژ اختصاصی خودرو در این زمان نیستند؛ قبل از حرکت، وضعیت ایستگاه را بررسی کن.</p>
          </>}
        </section>
      </div>
    </main>
  </div>;
}
