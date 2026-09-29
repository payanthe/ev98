import { StrictMode, Suspense, lazy, useLayoutEffect } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./app/App";
import { stationSlugFromPath } from "./lib/station";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "./styles/global.css";

const StationPage = lazy(() => import("./features/station/StationPage"));
const TripPage = lazy(() => import("./features/trip/TripPage"));

function Root() {
  const slug = stationSlugFromPath(window.location.pathname);
  const trip = window.location.pathname.replace(/\/+$/, "") === "/trip";
  useLayoutEffect(() => {
    document.documentElement.classList.toggle("is-station-page", slug != null || trip);
    return () => document.documentElement.classList.remove("is-station-page");
  }, [slug, trip]);
  if (trip) return <Suspense fallback={<div className="station-boot" role="status">در حال باز کردن برنامه‌ریز سفر</div>}><TripPage /></Suspense>;
  if (!slug) return <App />;
  return (
    <Suspense fallback={<div className="station-boot" role="status">در حال باز کردن ایستگاه</div>}>
      <StationPage slug={slug} />
    </Suspense>
  );
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Root />
    </QueryClientProvider>
  </StrictMode>,
);
