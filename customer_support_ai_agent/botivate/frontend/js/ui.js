// Everything that draws things on the screen. No network calls here.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const bold = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
const inr = (n) => "₹" + Math.round(n).toLocaleString("en-IN");
const badgeClass = (s) => "b-" + String(s).toLowerCase().replace(/[^a-z]+/g, "-");

// ---------- Agent info (used by the flow diagram + guide) ----------
const AGENTS = {
  user:         { name: "Customer",     text: "You! Your message starts the whole process." },
  orchestrator: { name: "Orchestrator", text: "The traffic controller. Reads your message and decides which agents are needed." },
  order:        { name: "Order Agent",  text: "Looks up order status, tracking and delivery, and can cancel an order." },
  support:      { name: "Support Agent",text: "Classifies problems, checks tickets, and creates new tickets." },
  product:      { name: "Product Agent",text: "Knows price, stock, warranty and whether an item is returnable." },
  resolution:   { name: "Resolution Agent", text: "The decision maker. Combines everything found and picks the next step: answer, ask, cancel, create a ticket or escalate." },
  handoff:      { name: "Human Handoff Agent", text: "Passes tricky or angry cases to a real person, with the full context attached." },
};
const AGENT_KEY = { "Orchestrator": "orchestrator", "Order Agent": "order", "Support Agent": "support",
                    "Product Agent": "product", "Resolution Agent": "resolution", "Handoff Agent": "handoff" };

// ---------- Chat ----------
function addMessage(text, who, extraClass = "") {
  const row = document.createElement("div");
  row.className = `row ${who}`;
  row.innerHTML = `<span class="avatar">${who === "bot" ? "🤖" : "👤"}</span>`;
  const d = document.createElement("div");
  d.className = `msg ${who} ${extraClass}`;
  d.innerHTML = who === "bot" ? bold(text) : esc(text);
  row.appendChild(d);
  $("log").appendChild(row);
  scrollChat();
  return d;
}
const scrollChat = () => { $("log").scrollTop = $("log").scrollHeight; };

function showTyping() {
  const row = document.createElement("div");
  row.className = "row bot"; row.id = "typing";
  row.innerHTML = '<span class="avatar">🤖</span><div class="msg bot skel"><i></i><i></i><i></i></div>';
  $("log").appendChild(row); scrollChat();
}
const hideTyping = () => $("typing")?.remove();

// ---------- Rich cards ----------
function renderCard(c) {
  const el = document.createElement("div");
  el.className = "card";
  if (c.type === "order") {
    const stepper = c.progress >= 0
      ? `<div class="stepper">${c.steps.map((s, i) =>
          `<div class="st ${i < c.progress ? "done" : i === c.progress ? "now" : ""}"><i></i><small>${esc(s)}</small></div>`).join("")}</div>`
      : "";
    el.innerHTML = `
      <div class="card-head"><b>📦 ${esc(c.order_id)}</b><span class="badge ${badgeClass(c.status)}">${esc(c.status)}</span></div>
      ${stepper}
      <div class="kv"><span>Total</span><b>${inr(c.total)}</b></div>
      <div class="kv"><span>Payment</span><b>${esc(c.payment_status)} · ${esc(c.payment_method)}</b></div>
      <div class="kv"><span>Expected</span><b>${esc(c.expected_delivery || "-")}${c.days_late ? ` <em class="late">(${c.days_late}d late)</em>` : ""}</b></div>
      ${c.tracking ? `<div class="kv"><span>Tracking</span><b>${esc(c.tracking)}</b></div>` : ""}
      <div class="items">${c.items.map((i) => `${i.qty}× ${esc(i.name)}`).join(" · ")}</div>`;
  } else if (c.type === "product") {
    el.innerHTML = `
      <div class="card-head"><b>🛍️ ${esc(c.name)}</b><span class="badge ${c.stock_label === "in stock" ? "b-ok" : "b-warn"}">${esc(c.stock_label)}</span></div>
      <div class="kv"><span>Price</span><b>${inr(c.price)}</b></div>
      <div class="kv"><span>Stock</span><b>${c.stock} units</b></div>
      <div class="kv"><span>Warranty</span><b>${c.warranty_months} months${c.warranty_until ? ` (until ${esc(c.warranty_until)})` : ""}</b></div>
      <div class="kv"><span>Returnable</span><b>${c.returnable ? "Yes" : "No"}</b></div>`;
  } else if (c.type === "ticket") {
    el.innerHTML = `
      <div class="card-head"><b>🎫 ${esc(c.ticket_id)}</b><span class="badge ${badgeClass(c.status)}">${esc(c.status)}</span></div>
      <div class="kv"><span>Issue</span><b>${esc(c.issue_type)}</b></div>
      <div class="kv"><span>Priority</span><b class="pri-${esc(c.priority)}">${esc(c.priority)}</b></div>
      <div class="kv"><span>Assigned to</span><b>${esc(c.assigned_to)}</b></div>`;
  } else if (c.type === "handoff") {
    el.classList.add("card-esc");
    el.innerHTML = `
      <div class="card-head"><b>🙋 Handed to a human</b><span class="badge b-escalated">${esc(c.priority)}</span></div>
      <div class="kv"><span>Ticket</span><b>${esc(c.ticket_id)}</b></div>
      <div class="kv"><span>Agent</span><b>${esc(c.assigned_to)}</b></div>
      <div class="why"><b>Why:</b><ul>${c.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>`;
  }
  return el;
}

function addCards(cards) {
  if (!cards?.length) return;
  const wrap = document.createElement("div");
  wrap.className = "cards";
  cards.forEach((c) => wrap.appendChild(renderCard(c)));
  $("log").appendChild(wrap); scrollChat();
}

// ---------- Suggestions ----------
function setSuggestions(list, onPick) {
  $("suggest").innerHTML = "";
  (list || []).forEach((t) => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = t;
    b.onclick = () => onPick(t);
    $("suggest").appendChild(b);
  });
}

// ---------- Sidebar ----------
function renderSidebar(ov, onOrderClick) {
  $("orders").innerHTML = "";
  ov.orders.forEach((o) => {
    const b = document.createElement("button");
    b.className = "chip";
    b.innerHTML = `<b>${esc(o.order_id)}</b> <span class="badge ${badgeClass(o.status)}">${esc(o.status)}</span><small>${inr(o.total_amount)} · ${esc(o.order_date)}</small>`;
    b.onclick = () => onOrderClick(o.order_id);
    $("orders").appendChild(b);
  });
  if (!ov.orders.length) $("orders").innerHTML = '<div class="muted">No orders yet</div>';
  $("tickets").innerHTML = ov.tickets.map((t) =>
    `<div class="tk"><b>${esc(t.ticket_id)}</b> <span class="badge ${badgeClass(t.status)}">${esc(t.status)}</span><small>${esc(t.issue_type)}</small></div>`
  ).join("") || '<div class="muted">No tickets</div>';
}

// ---------- Live agent flow ----------
const nodeEl = (key) => document.querySelector(`.node[data-agent="${key}"]`);
const allNodes = () => document.querySelectorAll(".node");

function resetFlow() {
  allNodes().forEach((n) => (n.className = "node"));
  $("timeline").innerHTML = "";
}
function flowThinking() {           // shown while waiting for the server
  resetFlow();
  nodeEl("user").classList.add("done");
  nodeEl("orchestrator").classList.add("active");
  $("timeline").innerHTML = '<div class="skel-rows"><i></i><i></i><i></i></div>';
}
function animateTrace(trace) {
  resetFlow();
  nodeEl("user").classList.add("done");
  trace.forEach((s, i) => {
    setTimeout(() => {
      const key = AGENT_KEY[s.agent];
      const n = nodeEl(key);
      if (n) { n.classList.remove("active"); n.classList.add(s.status === "escalate" ? "escalate" : s.status === "warn" ? "warn" : "done"); }
      const nxt = trace[i + 1] && nodeEl(AGENT_KEY[trace[i + 1].agent]);
      if (nxt && !nxt.classList.contains("done")) nxt.classList.add("active");
      const li = document.createElement("div");
      li.className = `step ${s.status}`;
      li.innerHTML = `<b>${esc(s.agent)}<span>${s.ms} ms</span></b><div>${esc(s.summary)}</div>`;
      $("timeline").appendChild(li);
      if (i === trace.length - 1) allNodes().forEach((x) => { if (x.className === "node") x.classList.add("skipped"); });
    }, i * 380);
  });
}
function showInfo(key) {
  const a = AGENTS[key];
  $("info").innerHTML = `<b>${a.name}</b><br>${a.text}`;
}

// ---------- Misc ----------
function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.h); toast.h = setTimeout(() => (t.hidden = true), 2600);
}
function fillAgentList() {
  $("agentList").innerHTML = Object.entries(AGENTS).filter(([k]) => k !== "user").map(([, a]) =>
    `<div class="al"><b>${a.name}</b><span>${a.text}</span></div>`).join("");
}

// Send button: normal / "pressed" loading state with spinner
function setSending(on) {
  const b = $("send");
  b.disabled = on;
  b.classList.toggle("loading", on);
  b.innerHTML = on ? '<i class="spin"></i>Sending…' : "Send";
}