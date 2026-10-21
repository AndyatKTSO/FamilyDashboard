export async function onRequestPost(context) {
  const { request, env } = context;

  let body;

  try {
    body = await request.json();
  } catch {
    return jsonResponse(
      { error: "Ungültiges JSON" },
      400
    );
  }

  const date = String(body.date || "").trim();
  const message = String(body.message || "").trim();

  if (message.length > 500) {
    return jsonResponse(
      { error: "Nachricht ist zu lang." },
      400
    );
  }

  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return jsonResponse(
      { error: "Ungültiges Datum." },
      400
    );
  }

  if (!env.GITHUB_TOKEN) {
    return jsonResponse(
      { error: "GITHUB_TOKEN fehlt in Cloudflare." },
      500
    );
  }

  const owner = "AndyatKTSO";
  const repo = "FamilyDashboard";
  const path = "message.json";
  const branch = "main";

  const apiUrl =
    `https://api.github.com/repos/${owner}/${repo}/contents/${path}`;

  const githubHeaders = {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "FamilyDashboard-Message"
  };

  let sha = null;

  const existing = await fetch(
    `${apiUrl}?ref=${encodeURIComponent(branch)}`,
    {
      headers: githubHeaders
    }
  );

  if (existing.ok) {
    const current = await existing.json();
    sha = current.sha;
  } else if (existing.status !== 404) {
    return jsonResponse(
      {
        error: "message.json konnte nicht gelesen werden.",
        githubStatus: existing.status
      },
      502
    );
  }

  const fileContent =
    JSON.stringify(
      {
        date,
        message
      },
      null,
      2
    ) + "\n";

  const encodedContent = bytesToBase64(
    new TextEncoder().encode(fileContent)
  );

  const payload = {
    message: message
      ? "Update screensaver message"
      : "Clear screensaver message",
    content: encodedContent,
    branch
  };

  if (sha) {
    payload.sha = sha;
  }

  const update = await fetch(
    apiUrl,
    {
      method: "PUT",
      headers: {
        ...githubHeaders,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    }
  );

  if (!update.ok) {
    const detail = await update.text();

    return jsonResponse(
      {
        error: "GitHub konnte message.json nicht aktualisieren.",
        githubStatus: update.status,
        detail
      },
      502
    );
  }

  return jsonResponse(
    {
      ok: true,
      date,
      message
    },
    200
  );
}

export function onRequestGet() {
  return jsonResponse(
    {
      ok: true,
      service: "FamilyDashboard message API"
    },
    200
  );
}

function jsonResponse(data, status) {
  return new Response(
    JSON.stringify(data),
    {
      status,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store"
      }
    }
  );
}

function bytesToBase64(bytes) {
  let binary = "";

  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }

  return btoa(binary);
}
