document.addEventListener("DOMContentLoaded", () => {
  const header = document.getElementById("siteHeader");
  const nav = document.getElementById("primaryNav");
  const navToggle = document.querySelector(".mobile-nav-toggle");
  const overlay = document.getElementById("loadingOverlay");
  const loadingText = document.getElementById("loadingText");

  const updateHeader = () => header?.classList.toggle("scrolled", window.scrollY > 8);
  updateHeader();
  window.addEventListener("scroll", updateHeader, { passive: true });

  navToggle?.addEventListener("click", () => {
    const open = nav?.classList.toggle("open") ?? false;
    navToggle.setAttribute("aria-expanded", String(open));
  });

  document.addEventListener("click", (event) => {
    if (!nav?.classList.contains("open")) return;
    if (nav.contains(event.target) || navToggle?.contains(event.target)) return;
    nav.classList.remove("open");
    navToggle?.setAttribute("aria-expanded", "false");
  });

  document.querySelectorAll(".flash-close").forEach((button) => {
    button.addEventListener("click", () => button.closest(".flash")?.remove());
  });
  window.setTimeout(() => {
    document.querySelectorAll(".flash").forEach((flash) => {
      flash.style.opacity = "0";
      window.setTimeout(() => flash.remove(), 250);
    });
  }, 9000);

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = form.dataset.confirm || "Continue?";
      if (!window.confirm(message)) event.preventDefault();
    });
  });

  const stages = [
    "Opening the source and reading its crawl policy…",
    "Prioritising About, company and contact pages…",
    "Retrying transient failures and checking JavaScript rendering…",
    "Extracting contacts, social profiles and company facts…",
    "Running deterministic extraction and optional LLM enrichment…",
    "Calculating explainable prospect signals…",
    "Writing the structured record and immutable snapshot…",
  ];

  document.querySelectorAll("form[data-loading-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (event.defaultPrevented || !form.checkValidity() || !overlay) return;
      overlay.classList.remove("hidden");
      overlay.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
      let index = 0;
      if (loadingText) loadingText.textContent = form.dataset.loadingMessage || stages[0];
      window.setInterval(() => {
        index = (index + 1) % stages.length;
        if (loadingText) loadingText.textContent = stages[index];
      }, 4500);
      form.querySelectorAll("button, input, select").forEach((control) => {
        control.setAttribute("aria-disabled", "true");
      });
      form.querySelectorAll("button[type='submit']").forEach((button) => {
        button.disabled = true;
      });
    });
  });
});
