import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import type { VehicleCatalog, VehicleVariant } from "../../api/types";
import { formatNumber } from "../../lib/format";
import { findVehicle, variantMatches } from "../../lib/vehicles";
import { BrandMark } from "../../ui/BrandMark";
import { IconCar, IconClose, IconSearch } from "../../ui/icons";

function batteryLabel(variant: VehicleVariant): string | null {
  if (variant.battery_kwh_min == null) return null;
  const max = variant.battery_kwh_max;
  const text =
    max != null && max !== variant.battery_kwh_min
      ? `${formatNumber(variant.battery_kwh_min)}–${formatNumber(max)}`
      : formatNumber(variant.battery_kwh_min);
  return `${text} کیلووات‌ساعت`;
}

function specParts(variant: VehicleVariant): string[] {
  const parts = [variant.powertrain_label];
  const battery = batteryLabel(variant);
  if (battery) parts.push(battery);
  if (variant.range_km != null) {
    parts.push(`${formatNumber(variant.range_km)} کیلومتر`);
    if (variant.range_standard) parts.push(variant.range_standard);
  }
  if (variant.connectors.length > 0) {
    parts.push(variant.connectors.map((item) => item.display_name).join("، "));
  }
  return parts;
}

function SpecLine({ variant }: { variant: VehicleVariant }) {
  const parts = specParts(variant);
  return (
    <span className="vehicle-spec">
      {parts.map((part, index) => (
        <span key={`${part}-${index}`}>
          {index > 0 && (
            <span className="sep" aria-hidden="true">
              {" "}
              ·{" "}
            </span>
          )}
          {part}
        </span>
      ))}
    </span>
  );
}

export function VehiclePicker({
  catalog,
  loading,
  error,
  vehicleId,
  onSelect,
  onClear,
  onRetry,
}: {
  catalog: VehicleCatalog | undefined;
  loading: boolean;
  error: boolean;
  vehicleId: string | null;
  onSelect: (variant: VehicleVariant) => void;
  onClear: () => void;
  onRetry: () => void;
}) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const selected = findVehicle(catalog, vehicleId);

  const groups = useMemo(() => {
    if (!catalog) return [];
    return catalog.makes
      .map((make) => ({
        make,
        variants: make.models.flatMap((model) => model.variants).filter((variant) => variantMatches(variant.search, query)),
      }))
      .filter((group) => group.variants.length > 0);
  }, [catalog, query]);

  const flat = useMemo(() => groups.flatMap((group) => group.variants.map((variant) => ({ make: group.make, variant }))), [groups]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query, open]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function close(focusTrigger = true) {
    setOpen(false);
    setQuery("");
    if (focusTrigger) triggerRef.current?.focus();
  }

  function choose(variant: VehicleVariant) {
    onSelect(variant);
    close();
  }

  function onKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "ArrowDown" && flat.length > 0) {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % flat.length);
    } else if (event.key === "ArrowUp" && flat.length > 0) {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + flat.length) % flat.length);
    } else if (event.key === "Home" && flat.length > 0) {
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === "End" && flat.length > 0) {
      event.preventDefault();
      setActiveIndex(flat.length - 1);
    } else if (event.key === "Enter") {
      const item = flat[activeIndex] ?? flat[0];
      if (item) {
        event.preventDefault();
        choose(item.variant);
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  }

  const activeId = open && flat[activeIndex] ? `${listId}-${flat[activeIndex].variant.id}` : undefined;

  return (
    <div className="vehicle-picker" ref={rootRef}>
      <button
        type="button"
        ref={triggerRef}
        className={selected ? "vehicle-trigger is-on" : "vehicle-trigger"}
        aria-expanded={open}
        aria-controls={open ? "vehicle-dialog" : undefined}
        aria-haspopup="dialog"
        onClick={() => setOpen((current) => !current)}
      >
        {selected ? (
          <>
            <BrandMark icon={selected.make.icon} name={selected.make.name_en} />
            <span className="vehicle-name">{selected.variant.display_name}</span>
          </>
        ) : (
          <>
            <IconCar />
            انتخاب خودرو
          </>
        )}
      </button>
      {selected && (
        <button type="button" className="vehicle-clear" aria-label="حذف خودرو" onClick={onClear}>
          <IconClose />
        </button>
      )}
      {open && (
        <div className="vehicle-panel" id="vehicle-dialog" role="dialog" aria-label="انتخاب خودرو">
          <div className="vehicle-search">
            <IconSearch />
            <input
              ref={inputRef}
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={flat.length > 0}
              aria-controls={flat.length > 0 ? listId : undefined}
              aria-activedescendant={activeId}
              aria-label="جست‌وجوی خودرو"
              placeholder="برند، مدل یا واردکننده"
              value={query}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={onKeyDown}
            />
            {query && (
              <button type="button" className="vehicle-clear" aria-label="پاک کردن جست‌وجو" onClick={() => setQuery("")}>
                <IconClose />
              </button>
            )}
          </div>
          <div className="vehicle-list">
            {loading && <p>در حال خواندن فهرست خودروها…</p>}
            {error && (
              <p role="alert">
                فهرست خودروها دریافت نشد.
                <button type="button" onClick={onRetry}>
                  دوباره
                </button>
              </p>
            )}
            {!loading && !error && flat.length === 0 && <p>خودرویی با این نام پیدا نشد.</p>}
            {flat.length > 0 && (
              <ul id={listId} role="listbox" aria-label="خودروها">
                {groups.map((group) => (
                  <li key={group.make.slug}>
                    <p className="vehicle-make">
                      <BrandMark icon={group.make.icon} name={group.make.name_en} />
                      {group.make.name_fa}
                    </p>
                    <ul>
                      {group.variants.map((variant) => {
                        const index = flat.findIndex((item) => item.variant.id === variant.id);
                        const active = index === activeIndex;
                        return (
                          <li
                            key={variant.id}
                            id={`${listId}-${variant.id}`}
                            role="option"
                            aria-selected={active}
                            className={[active ? "is-active" : "", selected?.variant.id === variant.id ? "is-current" : ""]
                              .filter(Boolean)
                              .join(" ")}
                            onMouseEnter={() => setActiveIndex(index)}
                            onMouseDown={(event) => event.preventDefault()}
                            onClick={() => choose(variant)}
                          >
                            <b>{variant.model_name}{variant.model_year ? ` ${variant.model_year}` : ""}</b>
                            <SpecLine variant={variant} />
                            {variant.importer_name_fa && <span>{variant.importer_name_fa}</span>}
                            {variant.warnings[0] && <span className="vehicle-warning">{variant.warnings[0]}</span>}
                          </li>
                        );
                      })}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="vehicle-note">
            داده از eMapna است. نقشه جایگاه‌هایی را نشان می‌دهد که حداقل یک درگاه مشترک با خودرو داشته باشند.
          </p>
        </div>
      )}
    </div>
  );
}
