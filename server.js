import http from "node:http";

const PORT = Number(process.env.PORT || 8787);
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const OPENAI_MODEL = process.env.OPENAI_MODEL || "gpt-4.1-mini";

function sendJson(res, status, body) {
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS, GET",
    "Access-Control-Allow-Headers": "Content-Type"
  });
  res.end(JSON.stringify(body));
}

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString("utf8");
  return raw ? JSON.parse(raw) : {};
}

function buildPrompt({ command, title, url, pageText }) {
  return `
You are an AI browser assistant. The user gave this command:
"${command}"

Current page:
Title: ${title || "Untitled"}
URL: ${url || "Unknown"}

Page text:
${pageText}

Return a concise, useful result for the user's command.
If the user asks to summarize an article for a Google Doc, write a polished document-ready summary with:
- A title
- 5-8 bullet key points
- A short "Why it matters" paragraph
- Source URL
`.trim();
}

async function askOpenAI(payload) {
  if (!OPENAI_API_KEY) {
    throw new Error("OPENAI_API_KEY is not set. Run: $env:OPENAI_API_KEY=\"your_key_here\"");
  }

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${OPENAI_API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model: OPENAI_MODEL,
      input: buildPrompt(payload),
      temperature: 0.2
    })
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data?.error?.message || `OpenAI request failed with ${response.status}`);
  }

  return data.output_text || "No response text returned.";
}

const server = http.createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    return sendJson(res, 204, {});
  }

  if (req.method === "GET" && req.url === "/health") {
    return sendJson(res, 200, {
      ok: true,
      hasApiKey: Boolean(OPENAI_API_KEY)
    });
  }

  if (req.method === "POST" && req.url === "/command") {
    try {
      const body = await readJson(req);
      const result = await askOpenAI({
        command: String(body.command || "Summarize this page"),
        title: String(body.title || ""),
        url: String(body.url || ""),
        pageText: String(body.pageText || "").slice(0, 24000)
      });

      return sendJson(res, 200, {
        result,
        openGoogleDoc: /google doc|docs|document|paste/i.test(String(body.command || ""))
      });
    } catch (error) {
      return sendJson(res, 500, { error: error.message });
    }
  }

  return sendJson(res, 404, { error: "Not found" });
});

server.listen(PORT, () => {
  console.log(`Browser AI Copilot server running at http://localhost:${PORT}`);
  console.log(`API key loaded: ${OPENAI_API_KEY ? "yes" : "no"}`);
  console.log(`Model: ${OPENAI_MODEL}`);
});