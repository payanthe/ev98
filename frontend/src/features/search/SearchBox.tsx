import { useEffect, useId, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchLocations } from "../../api/client";
import type { MapLocation } from "../../api/types";
import { EMPTY_FILTERS } from "../../lib/filters";
import { formatNumber } from "../../lib/format";
import { ConnectorMark, connectorIcon } from "../../ui/ConnectorMark";
import { IconClose, IconSearch } from "../../ui/icons";

export function SearchBox({ onSelect }: { onSelect: (location: MapLocation) => void }) {
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [composing, setComposing] = useState(false);
  const [focused, setFocused] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    if (composing) return;
    const timer = window.setTimeout(() => setDebounced(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [composing, query]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.isContentEditable || target.closest("input, textarea, select")) return;
      event.preventDefault();
      inputRef.current?.focus();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const search = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => fetchLocations(null, EMPTY_FILTERS, debounced),
    enabled: debounced.length >= 2,
  });

  const trimmed = query.trim();
  const pendingType = trimmed !== debounced && trimmed.length >= 2;
  const open = focused && trimmed.length >= 2;
  const waiting = pendingType || (debounced.length >= 2 && search.isFetching);
  const items = !waiting && !search.isError ? (search.data?.items ?? []) : [];

  useEffect(() => {
    setActiveIndex(0);
  }, [debounced]);

  useEffect(() => {
    if (!open || waiting || search.isError) return;
    const count = search.data?.items.length ?? 0;
    setAnnouncement(count === 0 ? "نتیجه‌ای پیدا نشد" : `${formatNumber(count)} نتیجه`);
  }, [open, search.data, search.isError, waiting]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setFocused(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function choose(location: MapLocation) {
    onSelect(location);
    setQuery("");
    setDebounced("");
    setFocused(false);
  }

  function onKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "ArrowDown" && items.length > 0) {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % items.length);
    } else if (event.key === "ArrowUp" && items.length > 0) {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + items.length) % items.length);
    } else if (event.key === "Home" && items.length > 0) {
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === "End" && items.length > 0) {
      event.preventDefault();
      setActiveIndex(items.length - 1);
    } else if (event.key === "Enter") {
      const item = items[activeIndex] ?? items[0];
      if (item) {
        event.preventDefault();
        choose(item);
      }
    } else if (event.key === "Escape" && (query || open)) {
      event.preventDefault();
      event.stopPropagation();
      if (query) setQuery("");
      setFocused(false);
    }
  }

  const activeId = open && items[activeIndex] ? `${listId}-${items[activeIndex].id}` : undefined;

  return (
    <div className="search" ref={rootRef}>
      <IconSearch />
      <input
        ref={inputRef}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={open && items.length > 0 ? listId : undefined}
        aria-activedescendant={activeId}
        aria-label="جست‌وجوی ایستگاه"
        placeholder="نام ایستگاه، شهر یا آدرس"
        value={query}
        autoComplete="off"
        spellCheck={false}
        enterKeyHint="search"
        onChange={(event) => {
          setQuery(event.target.value);
          setFocused(true);
        }}
        onFocus={() => setFocused(true)}
        onCompositionStart={() => setComposing(true)}
        onCompositionEnd={(event) => {
          setComposing(false);
          setQuery(event.currentTarget.value);
        }}
        onKeyDown={onKeyDown}
      />
      {query && (
        <button type="button" className="icon-button" aria-label="پاک کردن جست‌وجو" onClick={() => setQuery("")}>
          <IconClose />
        </button>
      )}
      <span className="visually-hidden" aria-live="polite">
        {announcement}
      </span>
      {open && (
        <div className="search-results" id={listId}>
          {waiting && <p>در حال جست‌وجو…</p>}
          {search.isError && !pendingType && (
            <p role="alert">جست‌وجو انجام نشد. نام را دوباره بنویسید.</p>
          )}
          {!waiting && !search.isError && items.length === 0 && (
            <p>نتیجه‌ای پیدا نشد. نام شهر، ایستگاه یا اپراتور را امتحان کنید.</p>
          )}
          {items.length > 0 && (
            <ul id={listId} role="listbox" aria-label="نتایج جست‌وجو">
              {items.map((item, index) => (
                <li
                  key={item.id}
                  id={`${listId}-${item.id}`}
                  role="option"
                  aria-selected={index === activeIndex}
                  className={index === activeIndex ? "is-active" : ""}
                  onMouseEnter={() => setActiveIndex(index)}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(item)}
                >
                  <b>{item.name}</b>
                  {/* Phase 1: بدون نمایش وضعیت شارژ در نتایج جستجو */}
                  <span>{item.city || item.operator_name || ""}</span>
                  <PlugRow standards={item.connector_standards} labels={item.connector_labels} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function PlugRow({ standards, labels }: { standards: string[]; labels: string[] }) {
  const plugs = [...new Map(standards.map((standard, index) => [standard, labels[index] || standard])).entries()];
  if (plugs.length === 0) return null;
  return (
    <span className="result-plugs">
      {plugs.map(([standard, label]) =>
        connectorIcon(standard) ? (
          <ConnectorMark key={standard} standard={standard} label={label} labelled />
        ) : (
          <span key={standard} className="plug-fallback">
            {label}
          </span>
        ),
      )}
    </span>
  );
}
