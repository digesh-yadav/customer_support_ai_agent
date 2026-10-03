// Main logic: wires the UI to the API.
let customerId = null;
let busy = false;

async function init() {
  fillAgentList();
  applyTheme(localStorage.getItem("theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  document.querySelectorAll(".node").forEach((n) => (n.onclick = () => showInfo(n.dataset.agent)));

  try {
    const h = await api.health();
    $("mode").textContent = h.llm ? "✨ Groq-powered" : "⚙️ Rule-based mode";
    $("mode").title = h.llm ? "Using the Groq API" : "No API key set - using built-in rules";
    const list = await api.customers();
    $("cust").innerHTML = list.map((c) =>
      `<option value="${c.customer_id}">${c.customer_id} · ${esc(c.name)} (${c.customer_tier})</option>`).join("");
    await switchCustomer();
  } catch (e) {
    $("mode").textContent = "❌ Backend offline";
    addMessage(`I can't reach the backend at ${API_BASE}.\nStart it with:  cd backend  →  python -m uvicorn app.main:app --port 8000`, "bot", "err");
  }
  if (!localStorage.getItem("seenGuide")) openGuide();
}

async function switchCustomer() {
  customerId = $("cust").value;
  $("log").innerHTML = "";
  resetFlow();
  $("timeline").innerHTML = '<div class="muted">Send a message to see each agent\'s step here.</div>';
  const ov = await api.overview(customerId);
  renderSidebar(ov, (id) => send(`Where is ${id}?`));
  const first = ov.orders[0]?.order_id || "ORD00001";
  addMessage("Hi! I'm your support assistant. I can track or cancel orders, answer product questions, and handle tickets. Try a suggestion below 👇", "bot");
  setSuggestions([`Where is ${first}?`, `Cancel ${first}`, "Price and warranty of Smart Watch", "Is Running Shoes in stock?",
                  `${first} arrived damaged`, "I want to talk to a human"], send);
}

async function send(text) {
  text = (text || "").trim();
  if (!text || busy) return;
  busy = true; setSending(true); $("msg").value = "";
  addMessage(text, "me");
  setSuggestions([], send);
  showTyping(); flowThinking(); showTab("agents");
  try {
    const r = await api.chat(customerId, text);
    hideTyping();
    addMessage(r.reply, "bot", r.decision === "escalate" ? "esc" : "");
    addCards(r.cards);
    animateTrace(r.trace);
    setSuggestions(r.suggestions, send);
    if (["escalate", "create_ticket", "cancel_executed"].includes(r.decision)) {
      renderSidebar(await api.overview(customerId), (id) => send(`Where is ${id}?`));
      toast(r.decision === "cancel_executed" ? "Order cancelled ✅" : r.decision === "create_ticket" ? "Ticket created 🎫" : "Escalated to a human 🙋");
    }
  } catch (e) {
    hideTyping(); resetFlow();
    addMessage("Something went wrong: " + e.message, "bot", "err");
  }
  busy = false; setSending(false); $("msg").focus();
}

function applyTheme(t) { document.documentElement.dataset.theme = t; localStorage.setItem("theme", t); }
function openGuide() { $("modal").hidden = false; }
function closeGuide() { $("modal").hidden = true; localStorage.setItem("seenGuide", "1"); }

$("form").addEventListener("submit", (e) => { e.preventDefault(); send($("msg").value); });
$("cust").addEventListener("change", switchCustomer);
$("helpBtn").onclick = openGuide;
$("closeModal").onclick = closeGuide;
$("themeBtn").onclick = () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
$("resetBtn").onclick = async () => { await api.reset(); await switchCustomer(); toast("Data restored ↺"); };

init();