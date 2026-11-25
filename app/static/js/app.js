// Smart Food Rescue — small page behaviours (no libraries needed).

// Mobile menu
document.querySelectorAll("[data-nav-toggle]").forEach((button) => {
  const nav = document.getElementById(button.getAttribute("aria-controls"));
  button.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    button.setAttribute("aria-expanded", String(open));
  });
});

// Dismiss flash messages
document.querySelectorAll("[data-dismiss]").forEach((button) => {
  button.addEventListener("click", () => button.closest(".flash").remove());
});

// Ask before destructive actions: <form data-confirm="Delete this listing?">
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

// Register page: the certificate upload is only for NGOs
const docField = document.getElementById("ngo-doc");
if (docField) {
  const sync = () => {
    const isNgo = document.getElementById("role-ngo").checked;
    docField.hidden = !isNgo;
    docField.querySelector("input").required = isNgo;
  };
  document.querySelectorAll('input[name="role"]').forEach((radio) => radio.addEventListener("change", sync));
  sync();
}

// Pickup countdowns: the server renders minutes left; we keep them ticking every minute.
const countdowns = document.querySelectorAll("[data-minutes-left]");
if (countdowns.length) {
  const loadedAt = Date.now();
  const label = (minutes) => {
    if (minutes <= 0) return "Pickup time has passed";
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    if (hours >= 24) return `${Math.floor(hours / 24)} d ${hours % 24} h left`;
    return hours ? `${hours} h ${mins} min left` : `${mins} min left`;
  };
  const tick = () => {
    const elapsed = Math.floor((Date.now() - loadedAt) / 60000);
    countdowns.forEach((el) => {
      const minutes = Number(el.dataset.minutesLeft) - elapsed;
      el.textContent = label(minutes);
      el.classList.toggle("soon", minutes > 0 && minutes <= 60);
      el.classList.toggle("gone", minutes <= 0);
    });
  };
  setInterval(tick, 60000);
}
