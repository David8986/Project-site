document.documentElement.classList.add("has-js");

const menuToggle = document.querySelector(".menu-toggle");
const siteNav = document.querySelector(".site-nav");

if (menuToggle && siteNav) {
  const closeMenu = () => {
    menuToggle.setAttribute("aria-expanded", "false");
    siteNav.classList.remove("is-open");
  };

  menuToggle.addEventListener("click", () => {
    const isOpen = menuToggle.getAttribute("aria-expanded") === "true";
    menuToggle.setAttribute("aria-expanded", String(!isOpen));
    siteNav.classList.toggle("is-open", !isOpen);
  });

  siteNav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

  const largeScreen = window.matchMedia("(min-width: 861px)");
  const resetMenuForDesktop = (event) => {
    if (event.matches) {
      closeMenu();
    }
  };

  if (typeof largeScreen.addEventListener === "function") {
    largeScreen.addEventListener("change", resetMenuForDesktop);
  } else if (typeof largeScreen.addListener === "function") {
    largeScreen.addListener(resetMenuForDesktop);
  }
}

const revealTargets = document.querySelectorAll(".reveal");

if (revealTargets.length > 0) {
  revealTargets.forEach((target, index) => {
    target.style.transitionDelay = `${Math.min(index * 45, 260)}ms`;
  });

  window.requestAnimationFrame(() => {
    window.setTimeout(() => {
      revealTargets.forEach((target) => {
        target.classList.add("is-visible");
      });
    }, 80);
  });
}
