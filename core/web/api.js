// Shared fetch helper. Same-origin only (the frontend is served by the same
// FastAPI app that owns /api/v1/*, see otherworld/api/main.py) — no CORS,
// the session cookie is just an ordinary same-origin cookie.
async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 401) {
    window.location.href = "/index.html";
    throw new Error("not signed in");
  }
  let data = null;
  try {
    data = await response.json();
  } catch (_e) {
    // no body
  }
  if (!response.ok) {
    const message = (data && (data.detail || data.error)) || `request failed (${response.status})`;
    throw new Error(message);
  }
  return data;
}

function showError(el, err) {
  el.textContent = err.message || String(err);
  el.style.display = "block";
}
