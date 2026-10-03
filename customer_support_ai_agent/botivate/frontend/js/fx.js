// Tabs + 3D effects (tilt on cards, parallax on spheres). No data logic here.
function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === name));
  document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("on", p.id === "tab-" + name));
}
document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => showTab(t.dataset.tab)));

// Only on mouse devices, and only if the user hasn't asked for less motion
if (matchMedia("(pointer:fine) and (prefers-reduced-motion:no-preference)").matches) {
  const orbs = document.querySelectorAll(".orb");
  document.addEventListener("mousemove", (e) => {
    const x = e.clientX / innerWidth - 0.5, y = e.clientY / innerHeight - 0.5;
    orbs.forEach((o) => (o.style.translate = `${-x * o.dataset.depth}px ${-y * o.dataset.depth}px`));
    const t = e.target.closest?.(".card,.chip");
    if (t) {
      const r = t.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5, py = (e.clientY - r.top) / r.height - 0.5;
      t.style.transform = `perspective(600px) rotateX(${-py * 10}deg) rotateY(${px * 12}deg) translateZ(6px)`;
    }
  });
  document.addEventListener("mouseout", (e) => {
    const t = e.target.closest?.(".card,.chip");
    if (t && !t.contains(e.relatedTarget)) t.style.transform = "";
  });
}