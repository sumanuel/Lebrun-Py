(function () {
  const sidebar = document.getElementById("sidebar");
  const toggle = document.getElementById("sidebarToggle");
  const search = document.getElementById("menuSearch");

  function isVisible(el) {
    if (!el) return false;
    return window.getComputedStyle(el).display !== "none";
  }

  function setOpen(body, chev, open) {
    if (body) body.style.display = open ? "" : "none";
    if (chev) chev.textContent = open ? "▾" : "▸";
  }

  function closeAllAccordions() {
    document.querySelectorAll(".menu__section").forEach((section) => {
      const body = section.querySelector(".menu__section-body");
      const chev = section.querySelector(
        ":scope > .menu__section-title .menu__chev"
      );
      setOpen(body, chev, false);

      section.querySelectorAll(".menu__group").forEach((group) => {
        const gBody = group.querySelector(".menu__group-body");
        const gChev = group.querySelector(
          ":scope > .menu__group-title .menu__chev"
        );
        setOpen(gBody, gChev, false);
      });
    });
  }

  function openAncestorsForActiveLink() {
    const active = document.querySelector(".menu__link.is-active");
    if (!active) return;

    const group = active.closest(".menu__group");
    if (group) {
      const gBody = group.querySelector(".menu__group-body");
      const gChev = group.querySelector(
        ":scope > .menu__group-title .menu__chev"
      );
      setOpen(gBody, gChev, true);
    }

    const section = active.closest(".menu__section");
    if (section) {
      const sBody = section.querySelector(".menu__section-body");
      const sChev = section.querySelector(
        ":scope > .menu__section-title .menu__chev"
      );
      setOpen(sBody, sChev, true);
    }
  }

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
      const isOpen = body && isVisible(body);
      setOpen(body, chev, !isOpen);
    });
  });

  // Accordion: colapsar/expandir submenús (grupos)
  document.querySelectorAll("[data-accordion-group]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const group = btn.closest(".menu__group");
      if (!group) return;
      const body = group.querySelector(".menu__group-body");
      const chev = group.querySelector(
        ":scope > .menu__group-title .menu__chev"
      );
      const isOpen = body && isVisible(body);
      setOpen(body, chev, !isOpen);
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
        li.hidden = !show;
      });

      // Ocultar grupos vacíos
      document.querySelectorAll(".menu__group").forEach((g) => {
        const visible = g.querySelectorAll(".menu__item:not([hidden])").length;
        g.style.display = visible ? "" : "none";

        if (q) {
          const gBody = g.querySelector(".menu__group-body");
          const gChev = g.querySelector(
            ":scope > .menu__group-title .menu__chev"
          );
          setOpen(gBody, gChev, visible > 0);
        }
      });

      // Ocultar módulos vacíos
      document.querySelectorAll(".menu__section").forEach((s) => {
        const visible = s.querySelectorAll(
          '.menu__group:not([style*="display: none"])'
        ).length;
        s.style.display = visible ? "" : "none";

        if (q) {
          const sBody = s.querySelector(".menu__section-body");
          const sChev = s.querySelector(
            ":scope > .menu__section-title .menu__chev"
          );
          setOpen(sBody, sChev, visible > 0);
        }
      });

      if (!q) {
        closeAllAccordions();
        openAncestorsForActiveLink();
      }
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

  // Estado inicial del menú: todo cerrado y solo se abre el item activo (si existe).
  closeAllAccordions();
  openAncestorsForActiveLink();
})();
