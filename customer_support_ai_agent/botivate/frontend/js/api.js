// All communication with the backend lives here.
async function request(path, options) {
  const res = await fetch(API_BASE + path, options);
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

const api = {
  health:    ()          => request("/api/health"),
  customers: ()          => request("/api/customers"),
  overview:  (id)        => request(`/api/customers/${id}/overview`),
  reset:     ()          => request("/api/reset", { method: "POST" }),
  chat:      (id, text)  => request("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customer_id: id, message: text }),
  }),
};
