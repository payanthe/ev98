import { useEffect, useId, useRef, useState } from "react";
import type { TripElevationProfile, TripProfileSegment, TripTerrainSpan } from "../../api/types";

const colors = {
  up: "#9b501c", down: "#226785", flat: "#607b72", battery: "#08705b",
  stop: "#9c611e", axis: "#536963", grid: "#dbe7e1", terrainFill: "#ecf3f0",
} as const;
const decimal = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 });
const sectionEnergy = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 3 });
const kilometers = (meters: number) => decimal.format(meters / 1000);
const percent = (soc: number) => `${decimal.format(soc)}٪`;
const HEIGHT = 334;
const LEFT = 45;
const RIGHT = 16;
const qualityStyles = {
  uncertain: { color: "#b56c00", fill: "rgba(181, 108, 0, .14)", label: "ارتفاع مشکوک", lane: 1 },
  bridge: { color: "#765399", fill: "rgba(118, 83, 153, .13)", label: "پل تخمینی", lane: 5 },
  tunnel: { color: "#3c536b", fill: "rgba(60, 83, 107, .15)", label: "تونل تخمینی", lane: 9 },
} as const;

function terrain(segment: TripProfileSegment) {
  const flat = segment.end_m - segment.start_m - segment.uphill_m - segment.downhill_m;
  if (segment.uphill_m > Math.max(segment.downhill_m, flat)) return "up";
  if (segment.downhill_m > Math.max(segment.uphill_m, flat)) return "down";
  return "flat";
}

function drawChart(canvas: HTMLCanvasElement, profile: TripElevationProfile, active: number) {
  const { width } = canvas.getBoundingClientRect();
  if (width <= LEFT + RIGHT) return;
  const pixelRatio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * pixelRatio);
  canvas.height = HEIGHT * pixelRatio;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.scale(pixelRatio, pixelRatio);
  ctx.font = `11px ${getComputedStyle(canvas).fontFamily}`;
  ctx.textBaseline = "middle";

  const { segments, stops } = profile;
  const length = segments.at(-1)?.end_m ?? 1;
  const elevations = segments.flatMap((s) => [s.start_elevation_m, s.end_elevation_m])
    .filter((value): value is number => value != null);
  const elevStep = Math.max(50, Math.ceil((Math.max(...elevations) - Math.min(...elevations)) / 100) * 50);
  const elevMin = Math.floor(Math.min(...elevations) / elevStep) * elevStep;
  const elevMax = Math.max(elevMin + elevStep, Math.ceil(Math.max(...elevations) / elevStep) * elevStep);
  const right = width - RIGHT;
  const x = (meters: number) => LEFT + meters / length * (right - LEFT);
  const elevationY = (meters: number) => 116 - (meters - elevMin) / (elevMax - elevMin) * 103;
  const socY = (soc: number) => 218 - soc / 100 * 65;
  const profiled = segments.filter((s) => s.resolution_m != null);
  const drawLimit = Math.max(.1, Math.ceil(Math.max(...profiled.map((s) => s.draw_kwh)) * 10) / 10);
  const regenLimit = Math.max(.01, Math.ceil(Math.max(...profiled.map((s) => s.regen_kwh)) * 100) / 100);
  const energyY = (kwh: number) => 275 - kwh / (kwh < 0 ? regenLimit : drawLimit) * 30;

  function line(x1: number, y1: number, x2: number, y2: number, color: string, thickness = 1) {
    ctx!.strokeStyle = color;
    ctx!.lineWidth = thickness;
    ctx!.beginPath();
    ctx!.moveTo(x1, y1);
    ctx!.lineTo(x2, y2);
    ctx!.stroke();
  }
  function yTick(y: number, label: string) {
    line(LEFT, y, right, y, colors.grid);
    ctx!.fillStyle = colors.axis;
    ctx!.textAlign = "right";
    ctx!.fillText(label, LEFT - 7, y);
  }
  const pick = segments[active];
  ctx.fillStyle = "#e4efe9";
  ctx.fillRect(x(pick.start_m), 10, Math.max(2, x(pick.end_m) - x(pick.start_m)), 299);
  for (const elevation of [elevMin, (elevMin + elevMax) / 2, elevMax])
    yTick(elevationY(elevation), decimal.format(elevation));
  for (const soc of [0, 50, 100]) yTick(socY(soc), percent(soc));
  yTick(energyY(drawLimit), decimal.format(drawLimit));
  yTick(energyY(0), "۰");
  yTick(energyY(-regenLimit), decimal.format(regenLimit));
  ctx.fillStyle = colors.axis;
  ctx.textAlign = "right";
  ctx.fillText("انرژی هر بخش (کیلووات‌ساعت)", right, 233);

  for (const s of segments) {
    const start = x(s.start_m), end = x(s.end_m);
    if (s.start_elevation_m != null && s.end_elevation_m != null) {
      const y1 = elevationY(s.start_elevation_m), y2 = elevationY(s.end_elevation_m);
      ctx.fillStyle = colors.terrainFill;
      ctx.beginPath();
      ctx.moveTo(start, 116);
      ctx.lineTo(start, y1);
      ctx.lineTo(end, y2);
      ctx.lineTo(end, 116);
      ctx.fill();
      line(start, y1, end, y2, colors[terrain(s)], 2.5);
    } else {
      ctx.setLineDash([3, 3]);
      line(start, 116, end, 116, colors.flat);
      ctx.setLineDash([]);
    }
    line(start, socY(s.start_soc), end, socY(s.end_soc), colors.battery, 2);
    if (s.resolution_m != null) {
      const barWidth = Math.max(.65, end - start - .35);
      ctx.fillStyle = colors.up;
      ctx.fillRect(start, energyY(s.draw_kwh), barWidth, energyY(0) - energyY(s.draw_kwh));
      ctx.fillStyle = colors.down;
      ctx.fillRect(start, energyY(0), barWidth, energyY(-s.regen_kwh) - energyY(0));
    }
  }

  for (const span of profile.quality_spans ?? []) {
    const left = x(span.start_m);
    const width = Math.min(right - left, Math.max(2, x(span.end_m) - left));
    const style = qualityStyles[span.kind];
    ctx.fillStyle = style.fill;
    ctx.fillRect(left, 13, width, 103);
    ctx.fillStyle = style.color;
    ctx.fillRect(left, style.lane, width, 3);
  }

  for (const stop of stops) {
    const at = x(stop.distance_m);
    ctx.setLineDash([4, 4]);
    line(at, 10, at, 308, colors.stop);
    ctx.setLineDash([]);
    line(at, socY(stop.arrival_soc), at, socY(stop.departure_soc), colors.stop, 3);
    ctx.fillStyle = colors.stop;
    ctx.beginPath();
    ctx.arc(at, socY(stop.departure_soc), 3.5, 0, 2 * Math.PI);
    ctx.fill();
  }

  const cursor = x((pick.start_m + pick.end_m) / 2);
  line(cursor, 10, cursor, 307, "#6f8c7d");
  const ticks = width < 440 ? 3 : 5;
  for (let index = 0; index < ticks; index++) {
    const dist = index * length / (ticks - 1);
    ctx.fillStyle = colors.axis;
    ctx.textAlign = index === 0 ? "left" : index === ticks - 1 ? "right" : "center";
    ctx.fillText(kilometers(dist), x(dist), 320);
  }
}

export function TripElevationChart({ profile }: { profile: TripElevationProfile }) {
  const titleId = useId();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [active, setActive] = useState(0);
  const { segments, stops } = profile;
  const selected = Math.max(0, Math.min(active, segments.length - 1));
  const segment = segments[selected];
  const length = segments.at(-1)?.end_m ?? 0;
  const stop = stops.find((item) => item.distance_m === segment?.end_m);
  const quality = profile.quality_spans ?? [];
  const kinds = (Object.keys(qualityStyles) as TripTerrainSpan["kind"][])
    .filter((kind) => quality.some((span) => span.kind === kind));
  const sectionKinds = segment ? kinds.filter((kind) => quality.some((span) =>
    span.kind === kind && span.start_m < segment.end_m && span.end_m > segment.start_m,
  )) : [];
  const direction = segment?.resolution_m == null ? "ارتفاع نامشخص" :
    { up: "بیشتر سربالایی", down: "بیشتر سرپایینی", flat: "بیشتر هموار" }[terrain(segment)];

  useEffect(() => {
    const node = canvas.current;
    if (!node || segments.length === 0) return;
    const render = () => drawChart(node, profile, selected);
    const observer = new ResizeObserver(render);
    observer.observe(node);
    render();
    return () => observer.disconnect();
  }, [profile, selected, segments.length]);

  function selectAt(clientX: number) {
    const bounds = canvas.current?.getBoundingClientRect();
    if (!bounds || bounds.width <= LEFT + RIGHT) return;
    const distance = (clientX - bounds.left - LEFT) / (bounds.width - LEFT - RIGHT) * length;
    selectDistance(distance);
  }
  function selectDistance(distance: number) {
    const next = segments.findIndex((item) => item.end_m >= distance);
    setActive(next < 0 ? segments.length - 1 : next);
  }
  function selectQuality(kind: TripTerrainSpan["kind"]) {
    const marks = quality.filter((span) => span.kind === kind);
    const next = marks.find((mark) => mark.start_m >= (segment?.end_m ?? 0)) ?? marks[0];
    if (next) selectDistance((next.start_m + next.end_m) / 2);
  }
  if (!segment) return null;

  return (
    <section className="trip-elevation" aria-labelledby={titleId}>
      <div className="trip-elevation-heading">
        <h3 id={titleId}>ارتفاع و شارژ در مسیر</h3>
        <span>مسافت از مبدأ</span>
      </div>
      <dl className="trip-elevation-totals">
        <div><dt><i className="is-up" />سربالایی</dt><dd>{kilometers(profile.uphill_m)} کیلومتر</dd></div>
        <div><dt><i className="is-down" />سرپایینی</dt><dd>{kilometers(profile.downhill_m)} کیلومتر</dd></div>
        <div><dt><i className="is-flat" />هموار</dt><dd>{kilometers(profile.mostly_flat_m)} کیلومتر</dd></div>
        <div><dt>بازیابی ترمز</dt><dd>{decimal.format(profile.regen_kwh)} کیلووات‌ساعت</dd></div>
      </dl>
      <div className="trip-elevation-key">
        <span>ارتفاع (متر)</span><span><i className="is-battery" />شارژ باتری</span><span><i className="is-stop" />توقف شارژ</span>
      </div>
      {kinds.length > 0 && <ul className="trip-elevation-quality" aria-label="علامت‌های کیفیت ارتفاع">
        {kinds.map((kind) => <li key={kind}>
          <button type="button" onClick={() => selectQuality(kind)}>
            <i className={`is-${kind}`} />{qualityStyles[kind].label}
          </button>
        </li>)}
      </ul>}
      <canvas ref={canvas} className="trip-elevation-canvas" aria-hidden="true"
        onPointerDown={(event) => selectAt(event.clientX)}
        onPointerMove={(event) => { if (event.pointerType === "mouse") selectAt(event.clientX); }} />
      <div className="trip-elevation-key trip-elevation-energy-key">
        <span><i className="is-up" />مصرف</span><span><i className="is-down" />بازیابی ترمز</span>
        <span>برای جزئیات، یک بخش را انتخاب کنید</span>
      </div>
      <input className="trip-elevation-slider" type="range" min={0} max={segments.length - 1} value={selected}
        dir="ltr" aria-label="انتخاب بخش مسیر"
        aria-valuetext={`کیلومتر ${kilometers(segment.start_m)} تا ${kilometers(segment.end_m)}`}
        onChange={(event) => setActive(Number(event.target.value))} />
      <div className="trip-elevation-inspection">
        <div className="trip-elevation-section-label">
          <strong>کیلومتر {kilometers(segment.start_m)} تا {kilometers(segment.end_m)}</strong>
          <small>{direction}{segment.start_elevation_m != null && segment.end_elevation_m != null &&
            ` · ارتفاع از ${decimal.format(segment.start_elevation_m)} تا ${decimal.format(segment.end_elevation_m)} متر`}</small>
        </div>
        <dl>
          <div><dt>مصرف این بخش</dt><dd>{sectionEnergy.format(segment.draw_kwh)} کیلووات‌ساعت</dd></div>
          <div><dt>بازیابی این بخش</dt><dd>{sectionEnergy.format(segment.regen_kwh)} کیلووات‌ساعت</dd></div>
          <div><dt>شارژ باتری</dt><dd>از {percent(segment.start_soc)} به {percent(segment.end_soc)}</dd></div>
        </dl>
        {sectionKinds.length > 0 && <ul className="trip-elevation-quality-details">
          {sectionKinds.map((kind) => <li key={kind}><i className={`is-${kind}`} />{
            kind === "uncertain" ? "ارتفاع این بخش به نمونه‌های کنار جاده حساس است." :
              kind === "bridge" ? "ارتفاع پل از مسیر پیرامون سازه برآورد شده." :
                "ارتفاع تونل از مسیر پیرامون سازه برآورد شده."
          }</li>)}
        </ul>}
        {stop && <p className="trip-elevation-stop-detail">
          {stop.name}، از {percent(stop.arrival_soc)} به {percent(stop.departure_soc)}
          {stop.charge_kwh != null && ` با ${decimal.format(stop.charge_kwh)} کیلووات‌ساعت شارژ`}
        </p>}
      </div>
      {stops.length > 0 && <ul className="trip-elevation-stops">
        {stops.map((item) => <li key={`${item.distance_m}-${item.name}`}>
          <button type="button" aria-pressed={item === stop}
            onClick={() => setActive(segments.findIndex((s) => s.end_m === item.distance_m))}>
            <i className="is-stop" />{item.name} <small>کیلومتر {kilometers(item.distance_m)}</small>
          </button>
        </li>)}
      </ul>}
      <p className="trip-elevation-note">
        محور مسافت از مبدأ شروع می‌شود. شیب کمتر از ۱٪ هموار حساب شده.
        {profile.unprofiled_m > 0 && ` دادهٔ ارتفاع برای ${kilometers(profile.unprofiled_m)} کیلومتر موجود نیست.`}
        {(profile.structures_unchecked_m ?? 0) > 0 &&
          ` سازه‌های ${kilometers(profile.structures_unchecked_m ?? 0)} کیلومتر از مسیر قابل بررسی نبودند.`}
      </p>
    </section>
  );
}
