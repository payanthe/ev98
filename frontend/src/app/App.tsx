import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ApiError, fetchLocation, fetchLocations } from "../api/client";
import type { BBox, LocationFilters, MapLocation } from "../api/types";
import { FilterBar } from "../features/filters/FilterBar";
import { DetailPanel } from "../features/location/DetailPanel";
import { MapCanvas } from "../features/map/MapCanvas";
import { MapStatus } from "../features/map/MapStatus";
import { SearchBox } from "../features/search/SearchBox";
import { SourceDrawer } from "../features/sources/SourceDrawer";
import { EMPTY_FILTERS, activeFilterCount, readMapState, writeMapState } from "../lib/filters";
import { useMediaQuery } from "../lib/useMediaQuery";
import { connectorsForQuery, findVehicle, useVehicleCatalog } from "../lib/vehicles";
import logo from "../assets/ev98-logo.png";

const initial = readMapState();

export function App() {
  const [bounds, setBounds] = useState<BBox | null>(null);
  const [filters, setFilters] = useState<LocationFilters>(initial.filters);
  const [selectedId, setSelectedId] = useState<string | null>(initial.selectedId);
  const [flyTarget, setFlyTarget] = useState<{ id: string; lat: number; lng: number } | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const isMobile = useMediaQuery("(max-width: 800px)");
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
    document.title = detail.data?.name ? `${detail.data.name} | EV98` : "EV98 | نقشه شارژ خودرو برقی";
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

  const onMapSelect = useCallback((id: string) => selectLocation(id), [selectLocation]);

  return (
    <div className={selectedId ? "shell has-detail" : "shell"}>
      <a className="skip" href="#map">
        رفتن به نقشه
      </a>
      <header className="topbar">
        <div className="brand">
          <img src={logo} alt="EV98" />
        </div>
        <SearchBox onSelect={(location) => selectLocation(location.id, location)} />
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
      </header>
      <FilterBar filters={filters} detailOpen={Boolean(selectedId)} onChange={setFilters}>
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
      <MapCanvas
        locations={items}
        selectedId={selectedId}
        flyTarget={flyTarget}
        panelOpen={Boolean(selectedId)}
        onBounds={setBounds}
        onSelect={onMapSelect}
        onNotice={setNotice}
      />
      <ul className="legend" aria-label="راهنمای وضعیت ایستگاه">
        <li>
          <i className="pin pin-available" aria-hidden="true" /> آزاد
        </li>
        <li>
          <i className="pin pin-charging" aria-hidden="true" /> در حال شارژ
        </li>
        <li>
          <i className="pin pin-unavailable" aria-hidden="true" /> خارج از دسترس
        </li>
        <li>
          <i className="pin pin-stale" aria-hidden="true" /> منقضی
        </li>
      </ul>
      {selectedId && (
        <DetailPanel
          location={detail.data}
          loading={detail.isLoading}
          error={detail.error instanceof ApiError ? detail.error.message : detail.error ? "جزئیات دریافت نشد" : null}
          vehicle={selectedVehicle?.variant ?? null}
          onClose={() => selectLocation(null)}
        />
      )}
      <SourceDrawer open={sourcesOpen} onClose={() => setSourcesOpen(false)} />
    </div>
  );
}
