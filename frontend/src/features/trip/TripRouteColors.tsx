import { useEffect } from "react";
import { Polyline, useMap } from "react-leaflet";
import type { TripRouteKind } from "../../api/types";
import type { RouteGroup, RouteMode, RoutePoint } from "./tripMapGeometry";

const styles = {
  consumption: { color: "#1856a8", dashArray: undefined, label: "مصرف خالص" },
  recovery: { color: "#16743f", dashArray: "7 5", label: "بازیابی خالص" },
  neutral: { color: "#57646c", dashArray: "2 5", label: "تغییر ناچیز" },
  uphill: { color: "#9b501c", dashArray: undefined, label: "سربالایی" },
  downhill: { color: "#226785", dashArray: "7 5", label: "سرپایینی" },
  level: { color: "#5b7169", dashArray: "2 5", label: "تقریباً هموار" },
  unknown: { color: "#707a83", dashArray: "1 7", label: "دادهٔ ناکافی" },
} satisfies Record<TripRouteKind, { color: string; dashArray?: string; label: string }>;
const legendOrder: TripRouteKind[] = ["consumption", "recovery", "neutral", "uphill", "downhill", "level", "unknown"];
const format = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });

export type RouteSelection = {
  kind: TripRouteKind | "overview";
  index: number;
  positions: RoutePoint[];
};

export function TripRouteLegend({ mode, groups, selection, hasStops, onMode, onFocus, onOverview }: {
  mode: RouteMode;
  groups: RouteGroup[];
  selection: RouteSelection | null;
  hasStops: boolean;
  onMode: (mode: RouteMode) => void;
  onFocus: (focus: RouteSelection) => void;
  onOverview: () => void;
}) {
  const shown = legendOrder.flatMap((kind) => groups.filter((group) => group.kind === kind));
  return (
    <div className="trip-route-legend">
      <div className="trip-route-toolbar">
        <div className="trip-route-modes" role="group" aria-label="نمای رنگی مسیر">
          <button type="button" aria-pressed={mode === "energy"} onClick={() => onMode("energy")}>جریان باتری</button>
          <button type="button" aria-pressed={mode === "slope"} onClick={() => onMode("slope")}>شیب مسیر</button>
        </div>
        <button className="trip-route-overview" type="button" onClick={onOverview}>کل مسیر</button>
      </div>
      <ul className="trip-route-key" aria-label={mode === "energy" ? "راهنمای جریان باتری" : "راهنمای شیب مسیر"}>
        {shown.map((group) => {
          const style = styles[group.kind];
          const distance = group.distance_m < 1000
            ? `${format.format(group.distance_m)} متر`
            : `${format.format(group.distance_m / 1000)} کیلومتر`;
          return <li key={group.kind}>
            <button type="button" title={`نمایش بخش ${style.label} روی نقشه`}
              onClick={() => {
                const index = selection?.kind === group.kind ? (selection.index + 1) % group.paths.length : 0;
                onFocus({ kind: group.kind, index, positions: group.paths[index] });
              }}>
              <i aria-hidden="true" style={{ borderColor: style.color,
                borderTopStyle: style.dashArray ? (style.dashArray.startsWith("7") ? "dashed" : "dotted") : "solid" }} />
              {style.label}<small>{distance}</small>
            </button>
          </li>;
        })}
        {hasStops && <li className="trip-route-stop-key"><i aria-hidden="true" />توقف شارژ</li>}
      </ul>
    </div>
  );
}

export function TripRouteLayers({ groups, outline }: { groups: RouteGroup[]; outline: RoutePoint[] }) {
  return <>
    <Polyline positions={outline} pathOptions={{ color: "#fff", weight: 9, opacity: .9, interactive: false }} />
    {[...groups].sort((a, b) => legendOrder.indexOf(a.kind) - legendOrder.indexOf(b.kind)).map(({ kind, paths }) => (
      <Polyline key={kind} positions={paths} smoothFactor={.5}
        pathOptions={{
          color: styles[kind].color, dashArray: styles[kind].dashArray,
          weight: 5.5, lineCap: "round", opacity: .98, interactive: false,
        }} />
    ))}
  </>;
}

export function RouteFocus({ selection }: { selection: RouteSelection | null }) {
  const map = useMap();
  useEffect(() => {
    if (selection && selection.positions.length > 1) {
      const options = selection.kind === "overview"
        ? { padding: [34, 34] as [number, number], animate: false }
        : { padding: [45, 45] as [number, number], maxZoom: 16, animate: false };
      map.fitBounds(selection.positions, options);
    }
  }, [map, selection]);
  return selection && selection.kind !== "overview" ? <Polyline positions={selection.positions}
    pathOptions={{
      color: styles[selection.kind].color, dashArray: styles[selection.kind].dashArray, weight: 7, interactive: false,
    }} /> : null;
}
