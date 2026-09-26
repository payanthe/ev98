import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import type { VehicleCatalog, VehicleVariant } from "../../api/types";
import { formatNumber } from "../../lib/format";
import { findVehicle, variantMatches } from "../../lib/vehicles";
import { BrandMark } from "../../ui/BrandMark";
import { IconCar, IconCheck, IconClose, IconSearch } from "../../ui/icons";

function batteryLabel(variant: VehicleVariant): string | null {
  if (variant.battery_kwh_min == null) return null;
  const max = variant.battery_kwh_max;
  const text =
    max != null && max !== variant.battery_kwh_min
      ? `${formatNumber(variant.battery_kwh_min)}–${formatNumber(max)}`
      : formatNumber(variant.battery_kwh_min);
  return `${text} کیلووات‌ساعت`;
}

function VehicleFacts({ variant }: { variant: VehicleVariant }) {
  const battery = batteryLabel(variant);
  return (
    <span className="vehicle-facts">
      <span className="vehicle-fact vehicle-powertrain">{variant.powertrain_label}</span>
      {battery && (
        <span className="vehicle-fact">
          <span className="vehicle-fact-label">باتری</span>
          <bdi>{battery.replace(" کیلووات‌ساعت", " kWh")}</bdi>
        </span>
      )}
      {variant.range_km != null && (
        <span className="vehicle-fact">
          <span className="vehicle-fact-label">برد</span>
          <bdi>{formatNumber(variant.range_km)} km</bdi>
          {variant.range_standard && <small dir="ltr">{variant.range_standard}</small>}
        </span>
      )}
      {variant.connectors.map((connector) => (
        <span className="vehicle-fact vehicle-connector" dir="ltr" key={connector.code}>
          {connector.display_name}
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
  const dialogId = useId();
  const titleId = useId();
  const searchId = useId();
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
  const variantIndexes = useMemo(
    () => new Map(flat.map((item, index) => [item.variant.id, index])),
    [flat],
  );

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

  useEffect(() => {
    if (!open) return;
    const active = flat[activeIndex];
    if (!active) return;
    document.getElementById(`${listId}-${active.variant.id}`)?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, flat, listId, open]);

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
        aria-controls={open ? dialogId : undefined}
        aria-haspopup="dialog"
        onClick={() => (open ? close(false) : setOpen(true))}
      >
        {selected ? (
          <>
            <BrandMark icon={selected.make.icon} name={selected.make.name_en} />
            <span className="vehicle-trigger-copy">
              <span className="vehicle-kicker">خودروی من</span>
              <span className="vehicle-name" dir="ltr">{selected.make.name_en} {selected.variant.model_name}</span>
            </span>
          </>
        ) : (
          <>
            <IconCar />
            <span className="vehicle-trigger-copy">
              <span className="vehicle-name">انتخاب خودروی من</span>
              <span className="vehicle-kicker">نمایش جایگاه‌های سازگار</span>
            </span>
          </>
        )}
      </button>
      {selected && (
        <button type="button" className="vehicle-clear" aria-label="حذف خودرو" onClick={onClear}>
          <IconClose />
        </button>
      )}
      {open && (
        <>
          <div className="vehicle-scrim" aria-hidden="true" onPointerDown={() => close()} />
          <div className="vehicle-panel" id={dialogId} role="dialog" aria-labelledby={titleId}>
            <header className="vehicle-panel-head">
              <div>
                <h2 id={titleId}>خودروی شما چیست؟</h2>
                <p>تا فقط شارژرهایی را ببینید که به خودروی شما می‌خورند.</p>
              </div>
              <button type="button" className="vehicle-panel-close" aria-label="بستن انتخاب خودرو" onClick={() => close()}>
                <IconClose />
              </button>
            </header>
            <label className="vehicle-search-label" htmlFor={searchId}>جست‌وجوی برند یا مدل</label>
            <div className="vehicle-search">
              <IconSearch />
              <input
                id={searchId}
                ref={inputRef}
                role="combobox"
                aria-autocomplete="list"
                aria-expanded={flat.length > 0}
                aria-controls={flat.length > 0 ? listId : undefined}
                aria-activedescendant={activeId}
                placeholder="مثلاً BYD یا E30X"
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
            {!loading && !error && (
              <p className="vehicle-results" aria-live="polite">
                {query
                  ? `${formatNumber(flat.length)} خودرو پیدا شد`
                  : `${formatNumber(flat.length)} خودرو از ${formatNumber(groups.length)} برند`}
              </p>
            )}
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
                      <span className="vehicle-make-names">
                        <b dir="ltr">{group.make.name_en}</b>
                        <span>{group.make.name_fa}</span>
                      </span>
                      <span className="vehicle-make-count">{formatNumber(group.variants.length)} مدل</span>
                    </p>
                    <ul>
                      {group.variants.map((variant) => {
                        const index = variantIndexes.get(variant.id) ?? 0;
                        const active = index === activeIndex;
                        const current = selected?.variant.id === variant.id;
                        return (
                          <li
                            key={variant.id}
                            id={`${listId}-${variant.id}`}
                            role="option"
                            aria-selected={current}
                            className={[active ? "is-active" : "", current ? "is-current" : ""]
                              .filter(Boolean)
                              .join(" ")}
                            onMouseEnter={() => setActiveIndex(index)}
                            onMouseDown={(event) => event.preventDefault()}
                            onClick={() => choose(variant)}
                          >
                            <span className="vehicle-option-title">
                              <b>
                                {variant.model_name}
                                {variant.model_year && <bdi className="vehicle-year">{variant.model_year}</bdi>}
                              </b>
                              {current && <span className="vehicle-current"><IconCheck /> انتخاب‌شده</span>}
                            </span>
                            <VehicleFacts variant={variant} />
                            {variant.importer_name_fa && (
                              <span className="vehicle-importer">
                                <span>واردکننده</span>
                                <b>{variant.importer_name_fa}</b>
                              </span>
                            )}
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
              با انتخاب خودرو، فیلتر کانکتورها خودکار تنظیم می‌شود. هر زمان بخواهید می‌توانید خودرو را تغییر دهید.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
