import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, useMap, useMapEvents } from "react-leaflet";
import "leaflet.markercluster";
import type { BBox, MapLocation } from "../../api/types";
import { formatNumber } from "../../lib/format";
import { IconCheck, IconClose, IconLocate, IconMapFit, IconMinus, IconPin, IconPlus } from "../../ui/icons";

const IRAN: L.LatLngBoundsExpression = [
  [25.0, 44.0],
  [39.8, 63.4],
];

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

type PinKind = "available" | "busy" | "offline" | "stale" | "operational" | "unknown";

// Phase 1: فقط محل ایستگاه‌ها — وضعیت زنده/در حال شارژ روی نقشه نشان داده نمی‌شود.
// پین واحد (operational = بدون وضعیت زنده) برای همه ایستگاه‌ها.
function pinKindFor(_location: MapLocation): PinKind {
  return "operational";
  // if (location.availability === "available") return "available";
  // if (location.availability === "charging") return "busy";
  // if (location.availability === "unavailable" || location.availability === "out_of_order") return "offline";
  // if (location.availability === "stale") return "stale";
  // if (location.availability === "operational") return "operational";
  // return "unknown";
}

function roundBox(box: BBox): BBox {
  const round = (value: number) => Math.round(value * 1000) / 1000;
  return { south: round(box.south), west: round(box.west), north: round(box.north), east: round(box.east) };
}

function iconFor(location: MapLocation, selected: boolean): L.DivIcon {
  const hasPower = location.max_power_kw != null;
  const power = hasPower ? String(Math.round(location.max_power_kw!)) : "—";
  const unit = hasPower ? "<small>kW</small>" : "";
  const kind = pinKindFor(location);
  const width = selected ? 72 : 52;
  const height = selected ? 91 : 66;
  return L.divIcon({
    className: `pin-wrap${selected ? " is-selected" : ""}`,
    html: `<div class="map-pin map-pin-${kind}${selected ? " is-selected" : ""}"><img src="/map-pins/station-${kind}.svg" alt="" /><span class="map-pin-power">${power}${unit}</span></div>`,
    iconSize: [width, height],
    iconAnchor: [width / 2, height - 5],
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
  onSelect: (location: MapLocation) => void;
}) {
  const map = useMap();
  const markersRef = useRef<Map<string, L.Marker>>(new Map());

  useEffect(() => {
    const group = L.markerClusterGroup({
      showCoverageOnHover: false,
      // Keep clusters only when zoomed far out (e.g. whole Iran).
      // At city scale (Tehran ~11–12) and closer, every station shows as its own pin.
      disableClusteringAtZoom: 11,
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
        // Phase 1: عنوان پین بدون وضعیت شارژ/آزاد بودن
        title: location.name,
        keyboard: true,
      });
      marker.on("click", () => onSelect(location));
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
  picking,
  onPickingChange,
  onSearchOrigin,
}: {
  panelOpen: boolean;
  autoCenter: boolean;
  onNotice: (message: string | null) => void;
  picking: boolean;
  onPickingChange: (value: boolean) => void;
  onSearchOrigin: (point: { lat: number; lng: number }) => void;
}) {
  const map = useMap();
  const markerRef = useRef<L.Marker | null>(null);
  const accuracyRef = useRef<L.Circle | null>(null);
  const autoTried = useRef(false);
  const panelOpenRef = useRef(panelOpen);
  const [locating, setLocating] = useState(false);
  const [hasLocation, setHasLocation] = useState(false);
  const [permissionPrompt, setPermissionPrompt] = useState(false);

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
    onSearchOrigin({ lat: latitude, lng: longitude });
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

  function requestLocate() {
    if (!navigator.geolocation) {
      onNotice("این مرورگر موقعیت را پشتیبانی نمی‌کند.");
      return;
    }
    const permissions = navigator.permissions;
    if (!permissions?.query) {
      setPermissionPrompt(true);
      return;
    }
    void permissions.query({ name: "geolocation" as PermissionName }).then((status) => {
      if (status.state === "granted") locate({ fly: true });
      else if (status.state === "denied") onNotice("دسترسی موقعیت قبلاً رد شده است. آن را از تنظیمات مرورگر فعال کنید.");
      else setPermissionPrompt(true);
    }).catch(() => setPermissionPrompt(true));
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
      <div className="map-tools-zoom" role="group" aria-label="زوم">
        <button type="button" className="icon-button" onClick={() => map.zoomIn()} aria-label="بزرگ‌نمایی" title="بزرگ‌نمایی">
          <IconPlus />
        </button>
        <button type="button" className="icon-button" onClick={() => map.zoomOut()} aria-label="کوچک‌نمایی" title="کوچک‌نمایی">
          <IconMinus />
        </button>
      </div>
      <button
        type="button"
        className={`map-tools-fab locate-button${hasLocation ? " is-active" : ""}`}
        onClick={requestLocate}
        disabled={locating}
        aria-busy={locating}
        aria-label="رفتن به ناحیه من"
        title="ناحیه من"
      >
        <IconLocate />
      </button>
      <button
        type="button"
        className={`map-tools-fab pick-location-button${picking ? " is-active" : ""}`}
        onClick={() => onPickingChange(!picking)}
        aria-pressed={picking}
        aria-label={picking ? "لغو انتخاب روی نقشه" : "انتخاب روی نقشه"}
        title={picking ? "لغو انتخاب" : "انتخاب روی نقشه"}
      >
        {picking ? <IconClose /> : <IconPin />}
      </button>
      <button
        type="button"
        className="map-tools-fab"
        onClick={() => map.fitBounds(IRAN, { animate: !reducedMotion, padding: [24, 24] })}
        aria-label="نمای ایران"
        title="نمای ایران"
      >
        <IconMapFit />
      </button>
      {permissionPrompt && (
        <div className="location-permission" role="dialog" aria-modal="true" aria-labelledby="location-permission-title">
          <span className="permission-icon"><IconLocate /></span>
          <strong id="location-permission-title">اجازه دسترسی به موقعیت</strong>
          <p>برای نمایش نزدیک‌ترین ایستگاه‌ها، مرورگر به اجازه موقعیت مکانی شما نیاز دارد.</p>
          <div>
            <button type="button" onClick={() => setPermissionPrompt(false)}>فعلاً نه</button>
            <button type="button" className="primary" onClick={() => { setPermissionPrompt(false); locate({ fly: true }); }}>
              <IconCheck /> ادامه
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function isMapSurfaceTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return !target.closest(
    ".map-tools, .leaflet-control, .leaflet-marker-icon, .leaflet-popup, .pick-location-hint, button, a, input, textarea, select",
  );
}

function ManualLocationPicker({ active, onPick }: { active: boolean; onPick: (point: { lat: number; lng: number }) => void }) {
  const map = useMap();
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;

  useMapEvents({
    click(event) {
      if (active) onPick({ lat: event.latlng.lat, lng: event.latlng.lng });
    },
    dblclick(event) {
      if (!isMapSurfaceTarget(event.originalEvent.target)) return;
      L.DomEvent.preventDefault(event);
      L.DomEvent.stopPropagation(event);
      onPick({ lat: event.latlng.lat, lng: event.latlng.lng });
    },
  });

  useEffect(() => {
    map.doubleClickZoom.disable();
    return () => {
      map.doubleClickZoom.enable();
    };
  }, [map]);

  // Mobile: long-press empty map to drop the nearby-search pin.
  useEffect(() => {
    const container = map.getContainer();
    const LONG_MS = 550;
    const MOVE_TOLERANCE = 14;
    let timer: number | null = null;
    let startClient: L.Point | null = null;
    let startLatLng: L.LatLng | null = null;
    let suppressContextMenu = false;
    let suppressTimer: number | null = null;

    function clearTimer() {
      if (timer != null) {
        window.clearTimeout(timer);
        timer = null;
      }
    }

    function resetGesture() {
      clearTimer();
      startClient = null;
      startLatLng = null;
    }

    function armContextMenuSuppress() {
      suppressContextMenu = true;
      if (suppressTimer != null) window.clearTimeout(suppressTimer);
      suppressTimer = window.setTimeout(() => {
        suppressContextMenu = false;
        suppressTimer = null;
      }, 450);
    }

    function onTouchStart(event: TouchEvent) {
      if (event.touches.length !== 1 || !isMapSurfaceTarget(event.target)) {
        resetGesture();
        return;
      }
      const touch = event.touches[0];
      startClient = L.point(touch.clientX, touch.clientY);
      startLatLng = map.mouseEventToLatLng(touch as unknown as MouseEvent);
      clearTimer();
      timer = window.setTimeout(() => {
        timer = null;
        if (!startLatLng) return;
        armContextMenuSuppress();
        onPickRef.current({ lat: startLatLng.lat, lng: startLatLng.lng });
        if (typeof navigator.vibrate === "function") navigator.vibrate(12);
        resetGesture();
      }, LONG_MS);
    }

    function onTouchMove(event: TouchEvent) {
      if (!startClient || event.touches.length !== 1) {
        resetGesture();
        return;
      }
      const touch = event.touches[0];
      if (startClient.distanceTo(L.point(touch.clientX, touch.clientY)) > MOVE_TOLERANCE) resetGesture();
    }

    function onTouchEnd() {
      resetGesture();
    }

    function onContextMenu(event: Event) {
      if (!suppressContextMenu) return;
      event.preventDefault();
      suppressContextMenu = false;
    }

    container.addEventListener("touchstart", onTouchStart, { passive: true });
    container.addEventListener("touchmove", onTouchMove, { passive: true });
    container.addEventListener("touchend", onTouchEnd);
    container.addEventListener("touchcancel", onTouchEnd);
    container.addEventListener("contextmenu", onContextMenu);
    return () => {
      resetGesture();
      if (suppressTimer != null) window.clearTimeout(suppressTimer);
      container.removeEventListener("touchstart", onTouchStart);
      container.removeEventListener("touchmove", onTouchMove);
      container.removeEventListener("touchend", onTouchEnd);
      container.removeEventListener("touchcancel", onTouchEnd);
      container.removeEventListener("contextmenu", onContextMenu);
    };
  }, [map]);

  return null;
}

function SearchOriginMarker({ point }: { point: { lat: number; lng: number } | null }) {
  const map = useMap();
  const marker = useRef<L.Marker | null>(null);
  useEffect(() => {
    if (!point) {
      marker.current?.remove();
      marker.current = null;
      return;
    }
    const icon = L.divIcon({
      className: "search-origin-wrap",
      html: '<div class="search-origin"><span></span></div>',
      iconSize: [38, 48],
      iconAnchor: [19, 44],
    });
    if (!marker.current) marker.current = L.marker([point.lat, point.lng], { icon, interactive: false, zIndexOffset: 1100 }).addTo(map);
    else marker.current.setLatLng([point.lat, point.lng]);
    return () => { marker.current?.remove(); marker.current = null; };
  }, [map, point]);
  return null;
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
  searchOrigin,
  onSearchOrigin,
}: {
  locations: MapLocation[];
  selectedId: string | null;
  flyTarget: { id: string; lat: number; lng: number } | null;
  panelOpen: boolean;
  autoCenterOnLocate?: boolean;
  onBounds: (box: BBox) => void;
  onSelect: (location: MapLocation) => void;
  onNotice: (message: string | null) => void;
  searchOrigin: { lat: number; lng: number } | null;
  onSearchOrigin: (point: { lat: number; lng: number }) => void;
}) {
  const [picking, setPicking] = useState(false);
  function pick(point: { lat: number; lng: number }) {
    onSearchOrigin(point);
    setPicking(false);
  }
  return (
    <MapContainer
      center={[35.7219, 51.405]}
      zoom={12}
      className={`map${picking ? " is-picking-location" : ""}`}
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
      <ManualLocationPicker active={picking} onPick={pick} />
      <SearchOriginMarker point={searchOrigin} />
      <FlyTo target={flyTarget} />
      <MapTools panelOpen={panelOpen} autoCenter={autoCenterOnLocate} onNotice={onNotice} picking={picking} onPickingChange={setPicking} onSearchOrigin={pick} />
      {picking && <div className="pick-location-hint" role="status"><IconPin /> نقطه موردنظرتان را روی نقشه انتخاب کنید</div>}
    </MapContainer>
  );
}
