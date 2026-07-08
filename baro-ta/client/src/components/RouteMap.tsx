import { useState } from "react";
import { RouteMapLeaflet } from "./RouteMapLeaflet";
import { RouteMapNaver } from "./RouteMapNaver";

/**
 * 출발→도착 경로 지도.
 *
 * [지도 구현 선택 지점] 네이버지도 키(VITE_NAVER_MAP_KEY_ID, client/.env)가 있으면
 * 네이버지도를 쓰고, 키가 없거나 SDK 로드·인증에 실패하면 키가 필요 없는
 * Leaflet(OSM)으로 자동 폴백한다 — 시연 중 외부 SDK 문제로 지도가 죽지 않게.
 * 지도 라이브러리는 RouteMap* 파일들 안에만 존재하고, 바깥은 역 이름만 넘긴다.
 */
const NAVER_KEY_ID: string | undefined = import.meta.env.VITE_NAVER_MAP_KEY_ID;

// 한 번 실패한 네이버지도는 세션 내 재시도하지 않는다 — 패널을 오갈 때마다
// 인증 실패 화면이 깜빡이는 것을 막는다 (모듈 레벨이라 리마운트에도 유지)
let naverUnavailable = false;

interface RouteMapProps {
  origin: string | null;
  dest: string | null;
}

export function RouteMap(props: RouteMapProps) {
  const [, bump] = useState(0);
  if (NAVER_KEY_ID && !naverUnavailable) {
    return (
      <RouteMapNaver
        {...props}
        keyId={NAVER_KEY_ID}
        onFail={() => {
          naverUnavailable = true;
          bump((n) => n + 1);
        }}
      />
    );
  }
  return <RouteMapLeaflet {...props} />;
}
