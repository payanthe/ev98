import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, useMap, useMapEvents } from "react-leaflet";
import "leaflet.markercluster";
import type { BBox, MapLocation } from "../../api/types";
import { formatNumber } from "../../lib/format";
import { IconLocate, IconMinus, IconPlus } from "../../ui/icons";

const IRAN: L.LatLngBoundsExpression = [
  [25.0, 44.0],
  [39.8, 63.4],
];

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function roundBox(box: BBox): BBox {
  const round = (value: number) => Math.round(value * 1000) / 1000;
  return { south: round(box.south), west: round(box.west), north: round(box.north), east: round(box.east) };
}

function iconFor(location: MapLocation, selected: boolean): L.DivIcon {
  const power = location.max_power_kw ? formatNumber(Math.round(location.max_power_kw)) : "•";
  return L.divIcon({
    className: "pin-wrap",
    html: `<div class="pin pin-${location.availability}${selected ? " is-selected" : ""}"><span>${power}</span></div>`,
    iconSize: [42, 42],
    iconAnchor: [21, 21],
  });
}

function moveView(map: L.Map, lat: number, lng: number, zoom: number, shiftForPanel: boolean) {
  const point = map.project([lat, lng], zoom);
  if (shiftForPanel) {
    const mobile = window.matchMedia("(max-width: 800px)").matches;
    if (mobile) point.y += Math.round(map.getSize().y * 0.3);
    else if (document.documentElement.dir === "rtl") point.x += 210;
    else point.x -= 210;
  }
  const center = map.unproject(point, zoom);
  if (reducedMotion) map.setView(center, zoom, { animate: false });
  else map.flyTo(center, zoom, { duration: 0.7 });
}

function MapTarget() {
  const map = useMap();
  useEffect(() => {
    const container = map.getContainer();
    container.id = "map";
    container.tabIndex = -1;
  }, [map]);
  return null;
}

function BoundsWatcher({ onChange }: { onChange: (box: BBox) => void }) {
  const map = useMapEvents({
    moveend() {
      const bounds = map.getBounds();
      onChange(
        roundBox({
          south: bounds.getSouth(),
          west: bounds.getWest(),
          north: bounds.getNorth(),
          east: bounds.getEast(),
        }),
      );
    },
  });
  useEffect(() => {
    const bounds = map.getBounds();
    onChange(
      roundBox({
        south: bounds.getSouth(),
        west: bounds.getWest(),
        north: bounds.getNorth(),
        east: bounds.getEast(),
      }),
    );
  }, [map, onChange]);
  return null;
}

function StationsLayer({
  locations,
  selectedId,
  onSelect,
}: {
  locations: MapLocation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const map = useMap();
  const markersRef = useRef<Map<string, L.Marker>>(new Map());

  useEffect(() => {
    const group = L.markerClusterGroup({
      showCoverageOnHover: false,
      maxClusterRadius: 46,
      spiderfyOnMaxZoom: true,
      iconCreateFunction(cluster) {
        return L.divIcon({
          className: "cluster-wrap",
          html: `<div class="cluster">${formatNumber(cluster.getChildCount())}</div>`,
          iconSize: [46, 46],
          iconAnchor: [23, 23],
        });
      },
    });
    const markers = new Map<string, L.Marker>();
    for (const location of locations) {
      const marker = L.marker([location.lat, location.lng], {
        icon: iconFor(location, false),
        title: `${location.name}، ${location.availability_label}`,
        keyboard: true,
      });
      marker.on("click", () => onSelect(location.id));
      markers.set(location.id, marker);
      group.addLayer(marker);
    }
    map.addLayer(group);
    markersRef.current = markers;
    return () => {
      map.removeLayer(group);
      markersRef.current = new Map();
    };
  }, [locations, map, onSelect]);

  useEffect(() => {
    const byId = new Map(locations.map((location) => [location.id, location]));
    for (const [id, marker] of markersRef.current) {
      const location = byId.get(id);
      if (!location) continue;
      marker.setIcon(iconFor(location, id === selectedId));
      marker.setZIndexOffset(id === selectedId ? 800 : 0);
    }
  }, [locations, selectedId]);

  return null;
}

function FlyTo({ target }: { target: { id: string; lat: number; lng: number } | null }) {
  const map = useMap();
  useEffect(() => {
    if (!target) return;
    const zoom = Math.max(map.getZoom(), window.matchMedia("(max-width: 800px)").matches ? 14 : 15);
    moveView(map, target.lat, target.lng, zoom, true);
  }, [map, target]);
  return null;
}

function MapTools({ panelOpen, onNotice }: { panelOpen: boolean; onNotice: (message: string | null) => void }) {
  const map = useMap();
  const markerRef = useRef<L.CircleMarker | null>(null);
  const [locating, setLocating] = useState(false);

  useEffect(() => {
    return () => {
      markerRef.current?.remove();
    };
  }, []);

  function locate() {
    if (!navigator.geolocation) {
      onNotice("این مرورگر موقعیت را پشتیبانی نمی‌کند.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        onNotice(null);
        const { latitude, longitude } = position.coords;
        const zoom = Math.max(map.getZoom(), 14);
        moveView(map, latitude, longitude, zoom, panelOpen);
        const latlng = L.latLng(latitude, longitude);
        if (!markerRef.current) {
          markerRef.current = L.circleMarker(latlng, {
            radius: 8,
            color: "#ffffff",
            weight: 3,
            fillColor: "#1f6b4a",
            fillOpacity: 1,
          }).addTo(map);
        } else {
          markerRef.current.setLatLng(latlng);
        }
      },
      () => {
        setLocating(false);
        onNotice("موقعیت در دسترس نیست. اجازه دسترسی را در مرورگر بررسی کنید.");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 15000 },
    );
  }

  return (
    <div
      className="map-tools"
      role="group"
      aria-label="کنترل نقشه"
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => event.stopPropagation()}
      onDoubleClick={(event) => event.stopPropagation()}
    >
      <button type="button" className="icon-button" onClick={() => map.zoomIn()} aria-label="بزرگ‌نمایی">
        <IconPlus />
      </button>
      <button type="button" className="icon-button" onClick={() => map.zoomOut()} aria-label="کوچک‌نمایی">
        <IconMinus />
      </button>
      <button type="button" onClick={() => map.fitBounds(IRAN, { animate: !reducedMotion, padding: [24, 24] })}>
        ایران
      </button>
      <button type="button" className="icon-button" onClick={locate} disabled={locating} aria-busy={locating} aria-label="نزدیک من">
        <IconLocate />
      </button>
    </div>
  );
}

export function MapCanvas({
  locations,
  selectedId,
  flyTarget,
  panelOpen,
  onBounds,
  onSelect,
  onNotice,
}: {
  locations: MapLocation[];
  selectedId: string | null;
  flyTarget: { id: string; lat: number; lng: number } | null;
  panelOpen: boolean;
  onBounds: (box: BBox) => void;
  onSelect: (id: string) => void;
  onNotice: (message: string | null) => void;
}) {
  return (
    <MapContainer
      center={[35.7219, 51.405]}
      zoom={12}
      className="map"
      zoomControl={false}
      zoomAnimation={!reducedMotion}
      fadeAnimation={!reducedMotion}
      markerZoomAnimation={!reducedMotion}
    >
      <MapTarget />
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <BoundsWatcher onChange={onBounds} />
      <StationsLayer locations={locations} selectedId={selectedId} onSelect={onSelect} />
      <FlyTo target={flyTarget} />
      <MapTools panelOpen={panelOpen} onNotice={onNotice} />
    </MapContainer>
  );
}
