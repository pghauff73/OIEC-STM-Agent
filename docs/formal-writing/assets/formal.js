(() => {
  "use strict";

  const root = document.documentElement;
  const themeButton = document.querySelector("[data-theme-toggle]");
  const themeLabel = document.querySelector("[data-theme-label]");
  const storageKey = "oiec-formal-writing-theme";
  const themes = ["system", "light", "dark"];

  const applyTheme = (theme) => {
    const next = themes.includes(theme) ? theme : "system";
    root.dataset.theme = next;
    if (themeLabel) {
      themeLabel.textContent = next === "system"
        ? "System"
        : next.charAt(0).toUpperCase() + next.slice(1);
    }
    if (themeButton) {
      themeButton.setAttribute("aria-label", `Colour theme: ${next}. Activate to change.`);
    }
  };

  let storedTheme = "system";
  try {
    storedTheme = localStorage.getItem(storageKey) || "system";
  } catch (_error) {
    storedTheme = "system";
  }
  applyTheme(storedTheme);

  themeButton?.addEventListener("click", () => {
    const currentIndex = themes.indexOf(root.dataset.theme || "system");
    const next = themes[(currentIndex + 1) % themes.length];
    applyTheme(next);
    try {
      localStorage.setItem(storageKey, next);
    } catch (_error) {
      // The preference is optional; the page remains fully usable without storage.
    }
  });

  const filterButtons = [...document.querySelectorAll("[data-source-filter]")];
  const sourceEntries = [...document.querySelectorAll("[data-source-class]")];

  filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const filter = button.dataset.sourceFilter || "all";
      filterButtons.forEach((candidate) => {
        const active = candidate === button;
        candidate.classList.toggle("active", active);
        candidate.setAttribute("aria-pressed", String(active));
      });
      sourceEntries.forEach((entry) => {
        entry.hidden = filter !== "all" && entry.dataset.sourceClass !== filter;
      });
    });
  });

  const copyStatus = document.querySelector("[data-copy-status]");
  let copyStatusTimer = null;

  const announce = (message) => {
    if (!copyStatus) return;
    copyStatus.textContent = message;
    copyStatus.classList.add("visible");
    window.clearTimeout(copyStatusTimer);
    copyStatusTimer = window.setTimeout(() => {
      copyStatus.classList.remove("visible");
    }, 1800);
  };

  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const targetId = button.dataset.copyTarget;
      const target = targetId ? document.getElementById(targetId) : null;
      if (!target) {
        announce("Copy target is unavailable.");
        return;
      }
      const text = target.textContent || "";
      try {
        await navigator.clipboard.writeText(text);
        announce("Command copied.");
      } catch (_error) {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(target);
        selection?.removeAllRanges();
        selection?.addRange(range);
        announce("Command selected. Copy it with your keyboard.");
      }
    });
  });

  const headerLinks = [...document.querySelectorAll(".site-header nav a[href^='#']")];
  const sections = headerLinks
    .map((link) => {
      const id = link.getAttribute("href")?.slice(1);
      const section = id ? document.getElementById(id) : null;
      return section ? { link, section } : null;
    })
    .filter(Boolean);

  if ("IntersectionObserver" in window && sections.length) {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!visible) return;
        sections.forEach(({ link, section }) => {
          if (section === visible.target) {
            link.setAttribute("aria-current", "true");
          } else {
            link.removeAttribute("aria-current");
          }
        });
      },
      { rootMargin: "-25% 0px -60% 0px", threshold: [0.05, 0.25, 0.6] }
    );
    sections.forEach(({ section }) => observer.observe(section));
  }
})();
