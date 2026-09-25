document.addEventListener("DOMContentLoaded", () => {
  const nameInput = document.getElementById("businessName");
  const urlInput = document.getElementById("sourceUrl");

  document.querySelectorAll("[data-sample-url]").forEach((button) => {
    button.addEventListener("click", () => {
      if (nameInput) nameInput.value = button.dataset.sampleName || "";
      if (urlInput) {
        urlInput.value = button.dataset.sampleUrl || "";
        urlInput.focus();
      }
      document.querySelector(".acquisition-form-card")?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "center",
      });
    });
  });
});

