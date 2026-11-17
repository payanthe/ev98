import { useEffect } from "react";
import { useMap } from "react-leaflet";
import { maplibreGL } from "@maplibre/maplibre-gl-leaflet";
import { addProtocol, setWorkerUrl, type StyleSpecification } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { layers, namedFlavor } from "@protomaps/basemaps";
import { Protocol } from "pmtiles";
import fontUrl from "vazirmatn/fonts/webfonts/Vazirmatn-Regular.woff2?url";
import "maplibre-gl/dist/maplibre-gl.css";

setWorkerUrl(workerUrl);
addProtocol("pmtiles", new Protocol().tile);

function iranStyle(): StyleSpecification {
  const font = new URL(fontUrl, location.href).href;
  const archive = new URL("/v1/trips/map/iran.pmtiles", location.origin).href;
  const baseLayers: StyleSpecification["layers"] = layers("iran", namedFlavor("light"), { lang: "fa" });
  return {
    version: 8,
    sources: { iran: { type: "vector", url: `pmtiles://${archive}` } },
    "font-faces": { Vazirmatn: [{ url: font }] },
    layers: baseLayers.flatMap((layer): StyleSpecification["layers"] => {
      if (layer.type !== "symbol") return [layer];
      const { "icon-image": _icon, ...layout } = layer.layout ?? {};
      if (!layout["text-field"]) return [];
      return [{ ...layer, layout: { ...layout, "text-font": ["Vazirmatn"] } }];
    }),
  };
}

export function TripBasemap({ onError }: { onError: (failed: boolean) => void }) {
  const map = useMap();
  useEffect(() => {
    const attribution = "© <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> · Protomaps";
    map.attributionControl?.addAttribution(attribution);
    const layer = maplibreGL({ style: iranStyle(), interactive: false });
    try {
      layer.addTo(map);
      const renderer = layer.getMaplibreMap();
      renderer.on("error", () => onError(true));
      renderer.once("load", () => onError(false));
    } catch {
      if (!layer.getMaplibreMap()) layer.onRemove = () => { layer.getContainer()?.remove(); return layer; };
      onError(true);
    }
    return () => {
      map.removeLayer(layer);
      map.attributionControl?.removeAttribution(attribution);
    };
  }, [map, onError]);
  return null;
}
