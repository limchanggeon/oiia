import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { STATION_COORDS, routeArc } from "../stations";

/**
 * 폴백 지도 구현: Leaflet + OpenStreetMap. API 키가 전혀 필요 없어
 * 네이버지도 키가 없거나 SDK 로드에 실패해도 데모가 항상 동작한다.
 */
interface RouteMapLeafletProps {
  origin: string | null;
  dest: string | null;
}

// styles.css의 --brand / --accent와 동일한 값
const BRAND = "#0C5C46";
const ACCENT = "#F5A300";

export function RouteMapLeaflet({ origin, dest }: RouteMapLeafletProps) {
  const divRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layersRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!divRef.current) return;
    const map = L.map(divRef.current, {
      scrollWheelZoom: false, // 페이지 스크롤을 지도가 가로채지 않도록
      zoomControl: true,
      attributionControl: true,
    });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);
    map.setView([36.35, 127.8], 7); // 한반도 남부 전경

    mapRef.current = map;
    const ro = new ResizeObserver(() => map.invalidateSize());
    ro.observe(divRef.current);
    return () => {
      ro.disconnect();
      try {
        map.remove();
      } catch {
        /* 애니메이션 진행 중 해제되면 leaflet이 던질 수 있다 */
      }
      mapRef.current = null;
      layersRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    layersRef.current?.remove();

    const from = origin ? STATION_COORDS[origin] : undefined;
    const to = dest ? STATION_COORDS[dest] : undefined;
    if (!from || !to) return;

    const station = (pos: [number, number], name: string, isDest: boolean) =>
      L.circleMarker(pos, {
        radius: 8,
        color: isDest ? ACCENT : BRAND,
        weight: 3,
        fillColor: "#fff",
        fillOpacity: 1,
      }).bindTooltip(`${name}${isDest ? " 도착" : " 출발"}`, {
        permanent: true,
        direction: isDest ? "bottom" : "top",
        offset: [0, isDest ? 10 : -10],
        className: `map-label${isDest ? " dest" : ""}`,
      });

    const group = L.layerGroup([
      L.polyline(routeArc(from, to), { color: BRAND, weight: 3.5, opacity: 0.9, dashArray: "1 7", lineCap: "round" }),
      station(from, origin!, false),
      station(to, dest!, true),
    ]).addTo(map);
    layersRef.current = group;

    map.fitBounds(L.latLngBounds([from, to]), { padding: [44, 44], maxZoom: 11, animate: false });
  }, [origin, dest]);

  if (!origin || !dest || !STATION_COORDS[origin] || !STATION_COORDS[dest]) return null;
  return <div ref={divRef} className="route-map" role="img" aria-label={`${origin}에서 ${dest}까지 경로 지도`} />;
}
