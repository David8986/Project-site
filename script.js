document.documentElement.classList.add("has-js");

const header = document.querySelector("[data-header]");
const menuButton = document.querySelector("[data-menu-button]");
const nav = document.querySelector("[data-nav]");

const setHeaderState = () => {
  if (!header) return;
  header.classList.toggle("is-scrolled", window.scrollY > 18);
};

setHeaderState();
window.addEventListener("scroll", setHeaderState, { passive: true });

if (menuButton && nav && header) {
  const closeMenu = () => {
    nav.classList.remove("is-open");
    header.classList.remove("is-open");
    document.body.classList.remove("is-menu-open");
    menuButton.setAttribute("aria-expanded", "false");
  };

  menuButton.addEventListener("click", () => {
    const shouldOpen = menuButton.getAttribute("aria-expanded") !== "true";
    nav.classList.toggle("is-open", shouldOpen);
    header.classList.toggle("is-open", shouldOpen);
    document.body.classList.toggle("is-menu-open", shouldOpen);
    menuButton.setAttribute("aria-expanded", String(shouldOpen));
  });

  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
  });

  const wideViewport = window.matchMedia("(min-width: 901px)");
  const syncMenu = (event) => {
    if (event.matches) closeMenu();
  };

  if (typeof wideViewport.addEventListener === "function") {
    wideViewport.addEventListener("change", syncMenu);
  } else if (typeof wideViewport.addListener === "function") {
    wideViewport.addListener(syncMenu);
  }
}

const revealTargets = document.querySelectorAll(".reveal");

if ("IntersectionObserver" in window && revealTargets.length) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    },
    {
      threshold: 0.14,
      rootMargin: "0px 0px -52px",
    }
  );

  revealTargets.forEach((target) => observer.observe(target));
} else {
  revealTargets.forEach((target) => target.classList.add("is-visible"));
}

document.querySelectorAll("[data-demo-form]").forEach((form) => {
  const status = form.querySelector("[data-form-status]");

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!status) return;

    status.textContent = form.getAttribute("data-success-message") || "Demo request noted.";
    status.hidden = false;
    form.reset();
  });
});
