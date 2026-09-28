import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ApiError, fetchLocation, fetchLocations, fetchNearbyLocations } from "../api/client";
import type { BBox, LocationFilters, MapLocation } from "../api/types";
import { FilterBar } from "../features/filters/FilterBar";
import { MapCanvas } from "../features/map/MapCanvas";
import { MapStatus } from "../features/map/MapStatus";
import { SearchBox } from "../features/search/SearchBox";
// Phase 1: منابع و مجوز به کاربر نشان داده نمی‌شود
// import { SourceDrawer } from "../features/sources/SourceDrawer";
import { EMPTY_FILTERS, activeFilterCount, readMapState, writeMapState } from "../lib/filters";
// import { useMediaQuery } from "../lib/useMediaQuery";
import { connectorsForQuery, findVehicle, useVehicleCatalog } from "../lib/vehicles";
import logo from "../assets/ev98-logo.webp";

const DetailPanel = lazy(() => import("../features/location/DetailPanel").then((module) => ({ default: module.DetailPanel })));
const NearbyStations = lazy(() => import("../features/location/NearbyStations").then((module) => ({ default: module.NearbyStations })));

const initial = readMapState();

export function App() {
  const [bounds, setBounds] = useState<BBox | null>(null);
  const [filters, setFilters] = useState<LocationFilters>(initial.filters);
  const [selectedId, setSelectedId] = useState<string | null>(initial.selectedId);
  const [flyTarget, setFlyTarget] = useState<{ id: string; lat: number; lng: number } | null>(null);
  // Phase 1: دراور منابع داده مخفی
  // const [sourcesOpen, setSourcesOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [searchOrigin, setSearchOrigin] = useState<{ lat: number; lng: number } | null>(null);
  // const isMobile = useMediaQuery("(max-width: 800px)");
  const opener = useRef<HTMLElement | null>(null);
  const flyFromUrl = useRef(Boolean(initial.selectedId));

  const vehicles = useVehicleCatalog();
  const selectedVehicle = useMemo(
    () => findVehicle(vehicles.data, filters.vehicleId),
    [vehicles.data, filters.vehicleId],
  );
  const queryFilters = useMemo<LocationFilters>(
    () => ({
      ...filters,
      connectors: connectorsForQuery(filters, selectedVehicle?.variant ?? null),
    }),
    [filters, selectedVehicle],
  );
  const waitingForVehicle = Boolean(filters.vehicleId) && vehicles.isLoading;

  const locations = useQuery({
    queryKey: ["locations", bounds, queryFilters],
    queryFn: () => fetchLocations(bounds, queryFilters),
    enabled: bounds !== null && !waitingForVehicle,
    placeholderData: keepPreviousData,
  });
  const detail = useQuery({
    queryKey: ["location", selectedId],
    queryFn: () => fetchLocation(selectedId!),
    enabled: Boolean(selectedId),
  });
  const nearby = useQuery({
    queryKey: ["nearby-locations", searchOrigin, queryFilters],
    queryFn: () => fetchNearbyLocations(searchOrigin!.lat, searchOrigin!.lng, queryFilters),
    enabled: searchOrigin !== null && !waitingForVehicle,
  });

  const items = locations.data?.items ?? [];
  const ready = bounds !== null;
  const errorMessage = locations.error
    ? locations.error instanceof ApiError
      ? locations.error.message
      : "ایستگاه‌ها دریافت نشدند"
    : null;

  useEffect(() => {
    writeMapState(selectedId, filters);
  }, [filters, selectedId]);

  useEffect(() => {
    if (!vehicles.isSuccess || !filters.vehicleId || selectedVehicle) return;
    setFilters((current) => (current.vehicleId ? { ...current, vehicleId: null } : current));
  }, [filters.vehicleId, selectedVehicle, vehicles.isSuccess]);

  useEffect(() => {
    const standards = selectedVehicle?.variant.station_standards;
    if (!standards) return;
    setFilters((current) => {
      const next = current.connectors.filter((id) => standards.includes(id));
      if (next.length === current.connectors.length) return current;
      return { ...current, connectors: next };
    });
  }, [selectedVehicle]);

  useEffect(() => {
    if (!flyFromUrl.current || !detail.data || detail.data.id !== selectedId) return;
    flyFromUrl.current = false;
    setFlyTarget({ id: detail.data.id, lat: detail.data.lat, lng: detail.data.lng });
  }, [detail.data, selectedId]);

  useEffect(() => {
    document.title = detail.data?.name
      ? `${detail.data.name} | EV98`
      : "EV98 | نقشه شارژ خودرو برقی ایران";
  }, [detail.data]);

  const selectLocation = useCallback((id: string | null, fly?: MapLocation) => {
    flyFromUrl.current = false;
    if (id) {
      if (document.activeElement instanceof HTMLElement && document.activeElement !== document.body) {
        opener.current = document.activeElement;
      }
      if (fly) setFlyTarget({ id: fly.id, lat: fly.lat, lng: fly.lng });
    } else if (opener.current?.isConnected) {
      opener.current.focus();
      opener.current = null;
    }
    setSelectedId(id);
  }, []);

  const onMapSelect = useCallback(
    (location: MapLocation) => selectLocation(location.id, location),
    [selectLocation],
  );

  const nearbyItems = nearby.data?.items ?? [];
  const nextNearbyStation = useMemo(() => {
    if (!searchOrigin || !selectedId || nearbyItems.length < 2) return null;
    const index = nearbyItems.findIndex((item) => item.id === selectedId);
    if (index < 0) return null;
    return nearbyItems[(index + 1) % nearbyItems.length] ?? null;
  }, [nearbyItems, searchOrigin, selectedId]);

  const onNextNearby = useCallback(() => {
    if (!nextNearbyStation) return;
    selectLocation(nextNearbyStation.id, nextNearbyStation);
  }, [nextNearbyStation, selectLocation]);

  return (
    <div className={`shell${selectedId ? " has-detail" : ""}${searchOrigin && !selectedId ? " has-nearby" : ""}`}>
      <a className="skip" href="#map">
        رفتن به نقشه
      </a>
      <header className="topbar">
        <div className="visually-hidden">
          <h1>نقشه ایستگاه‌های شارژ خودرو برقی ایران</h1>
          <p>ایستگاه شارژ نزدیک را پیدا کنید و توان، کانکتور و سازگاری آن با خودروی برقی خود را بررسی کنید.</p>
        </div>
        <div className="brand">
          <img src={logo} alt="EV98" width="240" height="62" />
        </div>
        <SearchBox onSelect={(location) => selectLocation(location.id, location)} />
        <a className="sources-button cars-nav" href="/cars/">
          خودروها
        </a>
        {/* Phase 1: دکمه «منابع داده» مخفی — منابع و مجوز به کاربر نشان داده نمی‌شود */}
        {/*
        <button
          type="button"
          className="sources-button"
          aria-label="منابع داده"
          aria-haspopup="dialog"
          aria-expanded={sourcesOpen}
          aria-controls={sourcesOpen ? "sources-dialog" : undefined}
          onClick={() => setSourcesOpen(true)}
        >
          {isMobile ? "منابع" : "منابع داده"}
        </button>
        */}
      </header>
      <FilterBar
        filters={filters}
        detailOpen={Boolean(selectedId)}
        nearbyOpen={Boolean(searchOrigin) && !selectedId}
        onChange={setFilters}
      >
        <MapStatus
          ready={ready}
          loading={waitingForVehicle || (ready && locations.isLoading)}
          updating={ready && locations.isFetching && !locations.isLoading}
          count={items.length}
          truncated={Boolean(locations.data?.truncated)}
          empty={ready && !waitingForVehicle && !locations.isFetching && !errorMessage && items.length === 0}
          filtered={activeFilterCount(filters) > 0}
          scope={selectedVehicle?.variant.display_name ?? null}
          error={errorMessage}
          notice={notice}
          onRetry={() => void locations.refetch()}
          onClear={() => setFilters(EMPTY_FILTERS)}
          onDismissNotice={() => setNotice(null)}
        />
      </FilterBar>
      <main className="map-stage" id="map" tabIndex={-1} aria-label="نقشه ایستگاه‌های شارژ">
        <MapCanvas
          locations={items}
          selectedId={selectedId}
          flyTarget={flyTarget}
          panelOpen={Boolean(selectedId)}
          autoCenterOnLocate={!selectedId}
          onBounds={setBounds}
          onSelect={onMapSelect}
          onNotice={setNotice}
          searchOrigin={searchOrigin}
          onSearchOrigin={setSearchOrigin}
        />
      </main>
      {/* Phase 1: راهنمای وضعیت شارژ مخفی — فقط محل ایستگاه‌ها؛ وضعیت زنده در فاز بعدی */}
      {/*
      <ul className="legend" aria-label="راهنمای وضعیت ایستگاه">
        <li>
          <img src="/map-pins/station-available.svg" alt="" aria-hidden="true" /> آزاد
        </li>
        <li>
          <img src="/map-pins/station-busy.svg" alt="" aria-hidden="true" /> در حال شارژ
        </li>
        <li>
          <img src="/map-pins/station-offline.svg" alt="" aria-hidden="true" /> خارج از دسترس
        </li>
        <li>
          <img src="/map-pins/station-operational.svg" alt="" aria-hidden="true" /> بدون وضعیت زنده
        </li>
        <li>
          <img src="/map-pins/station-stale.svg" alt="" aria-hidden="true" /> اطلاعات منقضی
        </li>
        <li>
          <img src="/map-pins/station-unknown.svg" alt="" aria-hidden="true" /> نامشخص
        </li>
      </ul>
      */}
      {selectedId && (
        <Suspense fallback={<div className="detail" role="status">در حال باز کردن جزئیات ایستگاه…</div>}>
          <DetailPanel
            location={detail.data}
            loading={detail.isLoading}
            error={detail.error instanceof ApiError ? detail.error.message : detail.error ? "جزئیات دریافت نشد" : null}
            vehicle={selectedVehicle?.variant ?? null}
            onClose={() => selectLocation(null)}
            onNextNearby={nextNearbyStation ? onNextNearby : undefined}
          />
        </Suspense>
      )}
      {searchOrigin && !selectedId && (
        <Suspense fallback={<div className="nearby-panel" role="status">در حال باز کردن ایستگاه‌های نزدیک…</div>}>
          <NearbyStations
            items={nearbyItems}
            loading={nearby.isLoading || nearby.isFetching}
            error={nearby.error instanceof ApiError ? nearby.error.message : nearby.error ? "ایستگاه‌های نزدیک دریافت نشدند." : null}
            onSelect={(location) => selectLocation(location.id, location)}
            onClose={() => setSearchOrigin(null)}
          />
        </Suspense>
      )}
      {/* Phase 1: دراور همگام‌سازی/منابع داده مخفی */}
      {/* <SourceDrawer open={sourcesOpen} onClose={() => setSourcesOpen(false)} /> */}
    </div>
  );
}
