import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchRun, fetchSources, startSync } from "../../api/client";
import type { SyncRun } from "../../api/types";
import { formatWhen } from "../../lib/format";

const FOCUSABLE = "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

function runStatusLabel(status: string): string {
  if (status === "succeeded") return "موفق";
  if (status === "failed") return "ناموفق";
  if (status === "running") return "در حال اجرا";
  if (status === "pending") return "در صف";
  return status;
}

export function SourceDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const dialogRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const sources = useQuery({ queryKey: ["sources"], queryFn: fetchSources, enabled: open });
  const [activeRun, setActiveRun] = useState<SyncRun | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const run = useQuery({
    queryKey: ["sync-run", activeRun?.id],
    queryFn: () => fetchRun(activeRun!.id),
    enabled: Boolean(activeRun && (activeRun.status === "pending" || activeRun.status === "running")),
    refetchInterval: 1500,
  });

  useEffect(() => {
    const current = run.data;
    if (!current) return;
    setActiveRun(current);
    if (current.status === "succeeded" || current.status === "failed") {
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
      void queryClient.invalidateQueries({ queryKey: ["locations"] });
      void queryClient.invalidateQueries({ queryKey: ["location"] });
    }
  }, [queryClient, run.data]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    const node = dialogRef.current;
    node?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !node) return;
      const items = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((element) => !element.hasAttribute("disabled"));
      if (items.length === 0) {
        event.preventDefault();
        node.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === node)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || active === node)) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, [open]);

  async function sync(source: string) {
    setMessage(null);
    try {
      const started = await startSync(source, true);
      setActiveRun(started);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "همگام‌سازی شروع نشد.");
    }
  }

  if (!open) return null;
  const current = run.data || activeRun;
  const busy = current?.status === "running" || current?.status === "pending";

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <section
        className="drawer"
        id="sources-dialog"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="sources-title"
        aria-describedby="sources-description"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <p className="eyebrow">منابع داده</p>
            <h2 id="sources-title">همگام‌سازی</h2>
          </div>
          <button type="button" onClick={onClose}>
            بستن
          </button>
        </header>
        <p className="muted" id="sources-description">
          نقشه مستقیم به سرویس‌دهنده‌ها وصل نمی‌شود. داده خام هر منبع نگه داشته می‌شود و ایستگاه روی نقشه موجودیت داخلی پلتفرم است.
        </p>
        <p className="muted">آیکن کانکتورها از Open Charge Map است، با پروانهٔ CC BY-SA 4.0.</p>
        {sources.isPending && <p>در حال دریافت منابع…</p>}
        {sources.isError && (
          <p className="error" role="alert">
            فهرست منابع دریافت نشد.
            <button type="button" onClick={() => void sources.refetch()}>
              تلاش دوباره
            </button>
          </p>
        )}
        {sources.data?.length === 0 && <p className="muted">منبعی ثبت نشده.</p>}
        {sources.data?.map((source) => (
          <article key={source.code} className="source-card">
            <div>
              <strong>{source.name}</strong>
              <span className="muted">{source.configured ? "آماده" : "کلید API ندارد"}</span>
            </div>
            <p>{source.attribution}</p>
            <p className="muted">
              {source.last_run
                ? `آخرین اجرا: ${runStatusLabel(source.last_run.status)} · ${formatWhen(source.last_run.finished_at || source.last_run.started_at)}`
                : "هنوز اجرا نشده"}
            </p>
            <button type="button" disabled={!source.configured || busy} onClick={() => sync(source.code)}>
              {busy ? "در حال به‌روزرسانی…" : `به‌روزرسانی ${source.name}`}
            </button>
          </article>
        ))}
        {current && (
          <div className="run">
            <strong>
              {current.status === "succeeded"
                ? "تمام شد"
                : current.status === "failed"
                  ? "ناموفق"
                  : current.status === "running"
                    ? "در حال دریافت"
                    : "در صف"}
            </strong>
            <span aria-live="polite">{progressText(current)}</span>
            {current.error && (
              <span className="error" role="alert">
                {current.error}
              </span>
            )}
          </div>
        )}
        {message && (
          <p className="error" role="alert">
            {message}
          </p>
        )}
      </section>
    </div>
  );
}

function progressText(run: SyncRun): string {
  const stats = run.stats || {};
  const phase = String(stats.phase || "");
  if (phase === "details") {
    return `جزئیات ${String(stats.details_done || 0)} از ${String(stats.listed || "…")}`;
  }
  if (phase === "persist") return "در حال ذخیره روی نقشه";
  if (phase === "done") {
    const locations = stats.locations ?? stats.persisted;
    return locations != null ? `${String(locations)} مکان پردازش شد` : "ذخیره شد";
  }
  if (phase === "fetch" || phase === "inventory") return "در حال دریافت فهرست";
  return phase || "در صف";
}
