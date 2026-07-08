import { useEffect, useRef } from "react";
import { STATION_COORDS, routeArc } from "../stations";

/**
 * 네이버지도(NCP Maps JS v3) 구현. SDK는 전역 window.naver로 주입되며
 * 공식 타입 선언이 없어 데모 범위에서는 any로 다룬다.
 */
declare global {
  interface Window {
    naver?: any;
    navermap_authFailure?: () => void;
  }
}

interface RouteMapNaverProps {
  origin: string | null;
  dest: string | null;
  keyId: string;
  onFail: () => void; // SDK 로드·인증 실패 → 상위에서 Leaflet으로 폴백
}

// styles.css의 --brand와 동일한 값
const BRAND = "#0C5C46";

// 인증 실패는 SDK 로드가 끝나고 지도 타일을 그리는 시점에 뒤늦게 올 수 있다.
// 언제 오든 마운트된 지도들이 폴백할 수 있도록 전역 훅을 구독 형태로 유지한다.
let authFailed = false;
const authListeners = new Set<() => void>();
if (typeof window !== "undefined") {
  window.navermap_authFailure = () => {
    authFailed = true;
    authListeners.forEach((fn) => fn());
  };
}

let sdkPromise: Promise<any> | null = null;
function loadNaverSdk(keyId: string): Promise<any> {
  if (window.naver?.maps?.Map) return Promise.resolve(window.naver);
  if (!sdkPromise) {
    sdkPromise = new Promise((resolve, reject) => {
      let settled = false;
      const fail = (msg: string) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        reject(new Error(msg));
      };
      const timer = window.setTimeout(() => fail("네이버지도 SDK 로드 시간 초과"), 8000);
      authListeners.add(() => fail("네이버지도 인증 실패 (키/서비스 URL 확인)"));
      const s = document.createElement("script");
      s.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${keyId}`;
      s.onerror = () => fail("네이버지도 SDK 로드 실패");
      s.onload = () => {
        // 인증 실패 콜백이 로드 직후 도착할 수 있어 잠시 기다렸다 판정
        window.setTimeout(() => {
          if (settled) return;
          if (window.naver?.maps?.Map) {
            settled = true;
            window.clearTimeout(timer);
            resolve(window.naver);
          } else {
            fail("네이버지도 초기화 실패");
          }
        }, 300);
      };
      document.head.appendChild(s);
    });
    sdkPromise.catch(() => {
      sdkPromise = null; // 다음 마운트에서 재시도 가능하게
    });
  }
  return sdkPromise;
}

export function RouteMapNaver({ origin, dest, keyId, onFail }: RouteMapNaverProps) {
  const divRef = useRef<HTMLDivElement | null>(null);
  const onFailRef = useRef(onFail);
  onFailRef.current = onFail;

  useEffect(() => {
    const el = divRef.current;
    const from = origin ? STATION_COORDS[origin] : undefined;
    const to = dest ? STATION_COORDS[dest] : undefined;
    if (!el || !from || !to) return;

    let disposed = false;
    let map: any = null;
    let ro: ResizeObserver | null = null;

    // 인증 실패가 지도 생성 이후에 도착해도 즉시 폴백
    const onAuth = () => {
      if (!disposed) onFailRef.current();
    };
    if (authFailed) {
      onAuth();
      return;
    }
    authListeners.add(onAuth);

    loadNaverSdk(keyId)
      .then((nv) => {
        // 인증 실패 상태의 SDK는 Map 생성·조작 중 내부 에러를 던진다 — 전부 폴백으로 흡수
        if (disposed) return;
        const ll = (p: [number, number]) => new nv.maps.LatLng(p[0], p[1]);
        map = new nv.maps.Map(el, {
          center: ll(from),
          zoom: 7,
          scrollWheel: false, // 페이지 스크롤을 지도가 가로채지 않도록
          zoomControl: true,
          zoomControlOptions: { position: nv.maps.Position.TOP_RIGHT },
        });
        new nv.maps.Polyline({
          map,
          path: routeArc(from, to).map(ll),
          strokeColor: BRAND,
          strokeWeight: 3.5,
          strokeOpacity: 0.9,
          strokeStyle: "shortdot",
          strokeLineCap: "round",
        });
        const pin = (p: [number, number], name: string, isDest: boolean) =>
          new nv.maps.Marker({
            map,
            position: ll(p),
            icon: {
              // stn-pin은 0×0 앵커 지점 — 점·라벨은 CSS transform으로 중앙 정렬
              content: `<div class="stn-pin${isDest ? " dest" : ""}"><div class="map-dot${isDest ? " dest" : ""}"></div><div class="map-label${isDest ? " dest" : ""}">${name} ${isDest ? "도착" : "출발"}</div></div>`,
              anchor: new nv.maps.Point(0, 0),
            },
          });
        pin(from, origin!, false);
        pin(to, dest!, true);

        const fit = () => {
          const b = new nv.maps.LatLngBounds(ll(from), ll(from)).extend(ll(to));
          map.fitBounds(b, { top: 48, right: 48, bottom: 48, left: 48 });
          if (map.getZoom() > 12) map.setZoom(12); // 인접 역 과확대 방지
        };
        fit();
        ro = new ResizeObserver(() => {
          try {
            nv.maps.Event.trigger(map, "resize");
            fit();
          } catch {
            /* 해제 직후 늦게 도착한 resize는 무시 */
          }
        });
        ro.observe(el);
      })
      .catch(() => {
        if (!disposed) onFailRef.current();
      });

    return () => {
      disposed = true;
      authListeners.delete(onAuth);
      ro?.disconnect();
      try {
        map?.destroy?.();
      } catch {
        /* 인증 실패 상태의 지도는 destroy도 던질 수 있다 */
      }
      if (el) el.innerHTML = "";
    };
  }, [origin, dest, keyId]);

  if (!origin || !dest || !STATION_COORDS[origin] || !STATION_COORDS[dest]) return null;
  return <div ref={divRef} className="route-map" role="img" aria-label={`${origin}에서 ${dest}까지 경로 지도`} />;
}
