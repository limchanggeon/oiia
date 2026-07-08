/**
 * 마이리얼트립 공식 MCP 서버 클라이언트 (https://mcp-servers.myrealtrip.com/mcp).
 * 인증 불필요 — JSON-RPC `tools/call`만 사용한다. 응답이 위젯 트리 + copy_text
 * 형태라, 위젯 항목에서 이름·평점·가격·링크·이미지를 추출해 카드로 정규화한다.
 */
const ENDPOINT = "https://mcp-servers.myrealtrip.com/mcp";

async function callTool(name, args) {
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }),
    signal: AbortSignal.timeout(12000),
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error.message || "MCP 오류");
  return JSON.parse(data.result.content[0].text);
}

// 위젯 항목 구조: Text 노드 [이름, "⭐ 4.6 (1,323)", "237,273원/박"] + Image + onClickAction.url
function extractCards(widgetJson, limit = 4) {
  const cards = [];
  for (const item of widgetJson?.widget?.children ?? []) {
    const texts = [];
    let img = null;
    (function walk(n) {
      if (Array.isArray(n)) return n.forEach(walk);
      if (!n || typeof n !== "object") return;
      if (n.type === "Text" && typeof n.value === "string") texts.push(n.value);
      if (n.type === "Image" && !img) img = n.src;
      walk(n.children);
    })(item);
    const url = item.onClickAction?.url ?? item.onClickAction?.payload?.target?.url ?? null;
    if (!texts.length || !url) continue;
    cards.push({
      name: texts[0],
      rating: texts.find((t) => t.startsWith("⭐")) ?? null,
      price: texts.find((t) => /원/.test(t)) ?? null,
      url,
      img,
    });
    if (cards.length >= limit) break;
  }
  return cards;
}

export async function suggestTravel({ dest, checkIn, checkOut }) {
  const [staysRes, tnasRes] = await Promise.allSettled([
    callTool("searchStays", { keyword: dest, checkIn, checkOut, isDomestic: true }),
    callTool("searchTnas", { query: dest, sort: "selling_count_desc" }),
  ]);
  return {
    stays: staysRes.status === "fulfilled" ? extractCards(staysRes.value) : [],
    tnas: tnasRes.status === "fulfilled" ? extractCards(tnasRes.value) : [],
  };
}
