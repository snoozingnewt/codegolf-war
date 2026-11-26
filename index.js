// Minimal remote MCP server (Streamable HTTP, JSON responses, no auth).
// Serves the small JSON files that the GitHub Action publishes to the repo's `data` branch.

const DATASETS = {
  weekly: "Weekly counts of hole×language cells led by AI, by humans, tied, AI-only and human-only.",
  cells: "Today's leader in every hole × language (bytes).",
  hole_month: "Per hole, % of contested languages led by AI / humans / tied, every 4 weeks.",
  lang_month: "Per language, % of solved holes held by AI alone / tied / humans, every 4 weeks.",
  meta: "When the data was last rebuilt.",
};

const TOOLS = [
  {
    name: "get_dataset",
    description:
      "Get one code.golf Humans-vs-AI dataset as {rows:[...]}. Datasets: " +
      Object.entries(DATASETS).map(([k, v]) => `${k} (${v})`).join("; "),
    inputSchema: {
      type: "object",
      properties: { name: { type: "string", enum: Object.keys(DATASETS) } },
      required: ["name"],
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
];

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
  "Access-Control-Allow-Headers": "*",
  "Access-Control-Expose-Headers": "Mcp-Session-Id",
};

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...CORS } });

async function handle(msg, env) {
  const { id, method, params } = msg;
  if (id === undefined || id === null) return null; // notification: no reply
  const ok = (result) => ({ jsonrpc: "2.0", id, result });
  const err = (code, message) => ({ jsonrpc: "2.0", id, error: { code, message } });

  switch (method) {
    case "initialize":
      return ok({
        protocolVersion: params?.protocolVersion || "2025-06-18",
        capabilities: { tools: {} },
        serverInfo: { name: "codegolf-war", version: "1.0.0" },
      });
    case "ping":
      return ok({});
    case "tools/list":
      return ok({ tools: TOOLS });
    case "tools/call": {
      if (params?.name !== "get_dataset") return err(-32602, "Unknown tool");
      const name = params?.arguments?.name;
      if (!DATASETS[name]) return err(-32602, "Unknown dataset: " + name);
      const url = `https://raw.githubusercontent.com/${env.REPO}/data/${name}.json`;
      const r = await fetch(url, { cf: { cacheTtl: 60, cacheEverything: true } });
      if (!r.ok) return ok({ isError: true, content: [{ type: "text", text: `Could not read ${url} (HTTP ${r.status})` }] });
      const text = await r.text();
      return ok({ content: [{ type: "text", text }] });
    }
    default:
      return err(-32601, "Method not found: " + method);
  }
}

export default {
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    if (req.method === "GET") return new Response("codegolf-war MCP server. POST JSON-RPC to /mcp.", { status: 405, headers: { Allow: "POST", ...CORS } });
    if (req.method !== "POST") return new Response("Method not allowed", { status: 405, headers: CORS });

    let body;
    try {
      body = await req.json();
    } catch {
      return json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }, 400);
    }
    if (Array.isArray(body)) {
      const out = (await Promise.all(body.map((m) => handle(m, env)))).filter(Boolean);
      return out.length ? json(out) : new Response(null, { status: 202, headers: CORS });
    }
    const out = await handle(body, env);
    return out ? json(out) : new Response(null, { status: 202, headers: CORS });
  },
};
