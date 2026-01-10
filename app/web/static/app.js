(function () {
  const sidebar = document.getElementById("sidebar");
  const toggle = document.getElementById("sidebarToggle");
  const search = document.getElementById("menuSearch");

  function setCollapsed(collapsed) {
    if (!sidebar) return;
    sidebar.classList.toggle("is-collapsed", collapsed);
    try {
      localStorage.setItem("lebrun.sidebar.collapsed", collapsed ? "1" : "0");
    } catch (_) {}
  }

  function restore() {
    if (!sidebar) return;
    try {
      const collapsed =
        localStorage.getItem("lebrun.sidebar.collapsed") === "1";
      setCollapsed(collapsed);
    } catch (_) {}

    if (window.matchMedia && window.matchMedia("(max-width: 900px)").matches) {
      sidebar.classList.add("is-hidden");
    }
  }

  if (toggle && sidebar) {
    toggle.addEventListener("click", function () {
      if (sidebar.classList.contains("is-hidden")) {
        sidebar.classList.remove("is-hidden");
        return;
      }
      setCollapsed(!sidebar.classList.contains("is-collapsed"));
    });
  }

  // Accordion: colapsar/expandir módulos
  document.querySelectorAll("[data-accordion]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const section = btn.closest(".menu__section");
      if (!section) return;
      const body = section.querySelector(".menu__section-body");
      const chev = section.querySelector(".menu__chev");
      const isOpen = body && body.style.display !== "none";
      if (body) body.style.display = isOpen ? "none" : "";
      if (chev) chev.textContent = isOpen ? "▸" : "▾";
    });
  });

  // Filtro de búsqueda en el menú
  if (search) {
    search.addEventListener("input", function () {
      const q = (search.value || "").trim().toLowerCase();
      const items = document.querySelectorAll(".menu__item");
      items.forEach((li) => {
        const label = (li.getAttribute("data-label") || "").toLowerCase();
        const show = !q || label.includes(q);
        li.style.display = show ? "" : "none";
      });

      // Ocultar grupos vacíos
      document.querySelectorAll(".menu__group").forEach((g) => {
        const visible = g.querySelectorAll(
          '.menu__item:not([style*="display: none"])'
        ).length;
        g.style.display = visible ? "" : "none";
      });

      // Ocultar módulos vacíos
      document.querySelectorAll(".menu__section").forEach((s) => {
        const visible = s.querySelectorAll(
          '.menu__group:not([style*="display: none"])'
        ).length;
        s.style.display = visible ? "" : "none";
      });
    });
  }

  // Cerrar sidebar en móvil si tocas fuera
  document.addEventListener("click", (e) => {
    if (!sidebar) return;
    if (!window.matchMedia || !window.matchMedia("(max-width: 900px)").matches)
      return;
    const target = e.target;
    if (target && sidebar.contains(target)) return;
    if (target && toggle && toggle.contains(target)) return;
    sidebar.classList.add("is-hidden");
  });

  restore();
})();
