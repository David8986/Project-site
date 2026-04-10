document.documentElement.classList.add("has-js");

// Replace these placeholder contact values once the customer's final contact pack is approved.
const siteContact = {
  phoneDisplay: "+40 700 000 000",
  phoneHref: "+40700000000",
  email: "contact@fansorspedition.ro",
  address: "Suceava, Romania",
  hours: {
    ro: "Luni - Vineri, 08:00 - 18:00",
    en: "Monday - Friday, 08:00 - 18:00",
  },
};

const pathSegments = window.location.pathname.split("/").filter(Boolean);
const currentFile = pathSegments[pathSegments.length - 1] || "index.html";
const currentLang = pathSegments.includes("en") ? "en" : "ro";
const navPanel = document.querySelector(".nav-panel");
const menuToggle = document.querySelector(".menu-toggle");

const setContactValue = (selector, value) => {
  document.querySelectorAll(selector).forEach((node) => {
    node.textContent = value;
  });
};

setContactValue("[data-site-phone-text]", siteContact.phoneDisplay);
setContactValue("[data-site-email-text]", siteContact.email);
setContactValue("[data-site-address-text]", siteContact.address);
setContactValue("[data-site-hours-text]", siteContact.hours[currentLang] || siteContact.hours.ro);

document.querySelectorAll("[data-site-phone-link]").forEach((link) => {
  link.href = `tel:${siteContact.phoneHref}`;
  link.setAttribute("aria-label", siteContact.phoneDisplay);
});

document.querySelectorAll("[data-site-email-link]").forEach((link) => {
  link.href = `mailto:${siteContact.email}`;
  link.setAttribute("aria-label", siteContact.email);
});

document.querySelectorAll("[data-year]").forEach((node) => {
  node.textContent = String(new Date().getFullYear());
});

document.querySelectorAll("[data-nav]").forEach((link) => {
  const isCurrent = link.getAttribute("data-nav") === currentFile;
  link.classList.toggle("is-current", isCurrent);
  if (isCurrent) {
    link.setAttribute("aria-current", "page");
  } else {
    link.removeAttribute("aria-current");
  }
});

document.querySelectorAll("[data-lang-link]").forEach((link) => {
  const targetLang = link.getAttribute("data-lang-link");
  if (targetLang === "ro" || targetLang === "en") {
    link.href = `../${targetLang}/${currentFile}`;
    const isActive = targetLang === currentLang;
    link.classList.toggle("is-active", isActive);
    if (isActive) {
      link.setAttribute("aria-current", "true");
    } else {
      link.removeAttribute("aria-current");
    }
  }
});

if (menuToggle && navPanel) {
  const closeMenu = () => {
    navPanel.classList.remove("is-open");
    menuToggle.setAttribute("aria-expanded", "false");
  };

  menuToggle.addEventListener("click", () => {
    const isOpen = menuToggle.getAttribute("aria-expanded") === "true";
    navPanel.classList.toggle("is-open", !isOpen);
    menuToggle.setAttribute("aria-expanded", String(!isOpen));
  });

  navPanel.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

  document.addEventListener("click", (event) => {
    if (!navPanel.classList.contains("is-open")) {
      return;
    }

    if (!navPanel.contains(event.target) && !menuToggle.contains(event.target)) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMenu();
    }
  });

  const largeScreen = window.matchMedia("(min-width: 881px)");
  const syncMenu = (event) => {
    if (event.matches) {
      closeMenu();
    }
  };

  if (typeof largeScreen.addEventListener === "function") {
    largeScreen.addEventListener("change", syncMenu);
  } else if (typeof largeScreen.addListener === "function") {
    largeScreen.addListener(syncMenu);
  }
}

const revealTargets = document.querySelectorAll(".reveal");

if ("IntersectionObserver" in window && revealTargets.length) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    {
      threshold: 0.14,
      rootMargin: "0px 0px -40px",
    }
  );

  revealTargets.forEach((target) => observer.observe(target));
} else {
  revealTargets.forEach((target) => target.classList.add("is-visible"));
}

// Connect the submission inside this listener when wiring the quote form to Netlify Forms, Formspree, or a custom backend.
document.querySelectorAll("[data-demo-form]").forEach((form) => {
  const status = form.querySelector("[data-form-status]");

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    if (!status) {
      return;
    }

    status.textContent = form.getAttribute("data-success-message") || "";
    status.hidden = false;
    form.reset();
  });
});
