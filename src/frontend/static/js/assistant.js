document.addEventListener("DOMContentLoaded", () => {
  const question = document.getElementById("assistantQuestion");
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!question) return;
      question.value = button.dataset.question || "";
      question.focus();
    });
  });
});
