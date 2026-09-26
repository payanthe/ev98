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

type PinKind = "available" | "busy" | "fast" | "offline";

function pinKindFor(location: MapLocation): PinKind {
  if (location.availability === "available") return "available";
  if (location.availability === "charging") return "busy";
  if (location.availability === "unavailable" || location.availability === "out_of_order") return "offline";
  if ((location.max_power_kw ?? 0) >= 50) return "fast";
  return "offline";
}

function roundBox(box: BBox): BBox {
  const round = (value: number) => Math.round(value * 1000) / 1000;
  return { south: round(box.south), west: round(box.west), north: round(box.north), east: round(box.east) };
}

function iconFor(location: MapLocation, selected: boolean): L.DivIcon {
  const power = location.max_power_kw ? formatNumber(Math.round(location.max_power_kw)) : "•";
  const kind = pinKindFor(location);
  return L.divIcon({
    className: "pin-wrap",
    html: `<div class="map-pin map-pin-${kind}${selected ? " is-selected" : ""}"><img src="/map-pins/station-${kind}.svg" alt="" /><span class="map-pin-power">${power}<small>kW</small></span></div>`,
    iconSize: [52, 66],
    iconAnchor: [26, 61],
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
          html: `<div class="map-cluster"><img src="/map-pins/station-cluster.svg" alt="" /><span>${formatNumber(cluster.getChildCount())}</span></div>`,
          iconSize: [64, 64],
          iconAnchor: [32, 32],
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

function userLocationIcon(): L.DivIcon {
  return L.divIcon({
    className: "user-loc-wrap",
    html: `<div class="user-loc" aria-hidden="true"><span class="user-loc-pulse"></span><span class="user-loc-dot"></span></div>`,
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  });
}

function locateErrorMessage(error: GeolocationPositionError): string {
  if (error.code === error.PERMISSION_DENIED) {
    return "اجازه موقعیت رد شد. از تنظیمات مرورگر دسترسی را فعال کنید.";
  }
  if (error.code === error.TIMEOUT) {
    return "دریافت موقعیت طول کشید. دوباره امتحان کنید.";
  }
  return "موقعیت در دسترس نیست. اتصال یا GPS را بررسی کنید.";
}

function MapTools({
  panelOpen,
  autoCenter,
  onNotice,
}: {
  panelOpen: boolean;
  autoCenter: boolean;
  onNotice: (message: string | null) => void;
}) {
  const map = useMap();
  const markerRef = useRef<L.Marker | null>(null);
  const accuracyRef = useRef<L.Circle | null>(null);
  const autoTried = useRef(false);
  const panelOpenRef = useRef(panelOpen);
  const [locating, setLocating] = useState(false);
  const [hasLocation, setHasLocation] = useState(false);

  panelOpenRef.current = panelOpen;

  useEffect(() => {
    return () => {
      markerRef.current?.remove();
      accuracyRef.current?.remove();
    };
  }, []);

  function showPosition(position: GeolocationPosition, fly: boolean) {
    const { latitude, longitude, accuracy } = position.coords;
    const latlng = L.latLng(latitude, longitude);

    if (!markerRef.current) {
      markerRef.current = L.marker(latlng, {
        icon: userLocationIcon(),
        interactive: false,
        keyboard: false,
        zIndexOffset: 1000,
      }).addTo(map);
    } else {
      markerRef.current.setLatLng(latlng);
    }

    const radius = Number.isFinite(accuracy) ? Math.max(24, Math.min(accuracy, 400)) : 48;
    if (!accuracyRef.current) {
      accuracyRef.current = L.circle(latlng, {
        radius,
        color: "#087a65",
        weight: 1,
        opacity: 0.45,
        fillColor: "#087a65",
        fillOpacity: 0.12,
        interactive: false,
      }).addTo(map);
    } else {
      accuracyRef.current.setLatLng(latlng);
      accuracyRef.current.setRadius(radius);
    }

    setHasLocation(true);
    onNotice(null);
    if (fly) {
      const zoom = Math.max(map.getZoom(), 14);
      moveView(map, latitude, longitude, zoom, panelOpenRef.current);
    }
  }

  function locate(options?: { fly?: boolean; quiet?: boolean }) {
    const fly = options?.fly ?? true;
    const quiet = options?.quiet ?? false;
    if (!navigator.geolocation) {
      if (!quiet) onNotice("این مرورگر موقعیت را پشتیبانی نمی‌کند.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        showPosition(position, fly);
      },
      (error) => {
        setLocating(false);
        if (!quiet) onNotice(locateErrorMessage(error));
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 },
    );
  }

  useEffect(() => {
    if (autoTried.current || !navigator.geolocation) return;
    autoTried.current = true;

    const permissions = navigator.permissions;
    if (!permissions?.query) return;

    void permissions
      .query({ name: "geolocation" as PermissionName })
      .then((status) => {
        if (status.state === "granted") locate({ fly: autoCenter, quiet: true });
      })
      .catch(() => {
        /* Permissions API may be unavailable for geolocation in some browsers. */
      });
    // Only auto-run once when the map tools mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, autoCenter]);

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
      <button
        type="button"
        className={`locate-button${hasLocation ? " is-active" : ""}`}
        onClick={() => locate({ fly: true })}
        disabled={locating}
        aria-busy={locating}
        aria-label="رفتن به ناحیه من"
        title="رفتن به ناحیه من"
      >
        <IconLocate />
        <span>ناحیه من</span>
      </button>
    </div>
  );
}

export function MapCanvas({
  locations,
  selectedId,
  flyTarget,
  panelOpen,
  autoCenterOnLocate = true,
  onBounds,
  onSelect,
  onNotice,
}: {
  locations: MapLocation[];
  selectedId: string | null;
  flyTarget: { id: string; lat: number; lng: number } | null;
  panelOpen: boolean;
  autoCenterOnLocate?: boolean;
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
      <MapTools panelOpen={panelOpen} autoCenter={autoCenterOnLocate} onNotice={onNotice} />
    </MapContainer>
  );
}
