(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const thoughtMessages = [
    "TRACE THE CLAIM TO ITS EVIDENCE.",
    "WHO OWNS THIS ARCHITECTURE FACT?",
    "BOUND AUTHORITY BEFORE EXECUTION.",
    "A PROJECTION MAY BE REBUILT; A FACT NEEDS PROVENANCE.",
    "WHAT TEST COULD DISPROVE THIS CLAIM?",
    "SEPARATE IMPLEMENTATION FROM CERTIFICATION.",
    "FAIL CLOSED WHEN THE EVIDENCE CHAIN BREAKS.",
    "MAKE THE RECOVERY PATH AS EXPLICIT AS SUCCESS.",
    "A DIAGRAM IS A HYPOTHESIS UNTIL THE SYSTEM CONFIRMS IT.",
    "LEAST PRIVILEGE IS AN ARCHITECTURE SHAPE.",
    "NAME THE COUNTERARGUMENT, THEN TEST IT.",
    "EXACT HASHES TURN 'SAME' INTO A CHECKABLE CLAIM."
  ];

  const query = (selector, root = document) => root.querySelector(selector);
  const queryAll = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function makeSvgElement(name, attributes = {}) {
    const element = document.createElementNS(SVG_NS, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
    return element;
  }

  function setButtonState(button, active, activeLabel, inactiveLabel) {
    if (!button) return;
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.textContent = active ? activeLabel : inactiveLabel;
  }

  function setupFocusMode() {
    const button = query('[data-action="focus-mode"]');
    if (!button) return;
    const saved = sessionStorage.getItem("ourd-docs-focus") === "true";
    document.body.classList.toggle("focus-mode", saved);
    setButtonState(button, saved, "EXIT FOCUS", "FOCUS");
    button.addEventListener("click", () => {
      const active = document.body.classList.toggle("focus-mode");
      sessionStorage.setItem("ourd-docs-focus", String(active));
      setButtonState(button, active, "EXIT FOCUS", "FOCUS");
    });
  }

  function setupEvidenceToggle() {
    const button = query('[data-action="collapse-evidence"]');
    if (!button) return;
    let expanded = false;
    setButtonState(button, expanded, "HIDE EVIDENCE", "EVIDENCE");
    button.addEventListener("click", () => {
      expanded = !expanded;
      queryAll(".source-evidence, .concept-lab").forEach((details) => {
        details.open = expanded;
      });
      setButtonState(button, expanded, "HIDE EVIDENCE", "EVIDENCE");
    });
  }

  function setupReadingProgress() {
    const progress = query(".reading-progress span");
    if (!progress) return;
    const update = () => {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      const ratio = scrollable > 0 ? Math.min(1, Math.max(0, window.scrollY / scrollable)) : 0;
      progress.style.width = `${ratio * 100}%`;
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
  }

  function setupTreeToggles() {
    queryAll(".tree-toggle").forEach((button) => {
      button.addEventListener("click", () => {
        const folder = button.closest(".tree-folder");
        if (!folder) return;
        const collapsed = folder.classList.toggle("is-collapsed");
        button.setAttribute("aria-expanded", collapsed ? "false" : "true");
        const icon = query(".tree-icon", button);
        if (icon) icon.textContent = collapsed ? "▸" : "▾";
      });
    });
  }

  function filterDocumentationTree(term) {
    const normalized = term.trim().toLowerCase();
    let visibleCount = 0;
    queryAll(".tree-document").forEach((item) => {
      const matches = !normalized || (item.dataset.search || "").includes(normalized);
      item.hidden = !matches;
      if (matches) visibleCount += 1;
    });
    queryAll(".tree-folder").forEach((folder) => {
      const hasVisibleChild = queryAll(".tree-document", folder).some((item) => !item.hidden);
      folder.hidden = !hasVisibleChild;
      if (normalized && hasVisibleChild) {
        folder.classList.remove("is-collapsed");
        const button = query(".tree-toggle", folder);
        if (button) button.setAttribute("aria-expanded", "true");
        const icon = query(".tree-icon", folder);
        if (icon) icon.textContent = "▾";
      }
    });
    const status = query(".search-status");
    if (status) {
      status.textContent = normalized
        ? `${visibleCount} DOCUMENT${visibleCount === 1 ? "" : "S"} MATCH “${term.trim()}”`
        : `${queryAll(".tree-document").length} DOCUMENTS ONLINE`;
    }
  }

  function setupIndexSearch() {
    const search = query("#docs-search");
    if (!search) return;
    filterDocumentationTree("");
    search.addEventListener("input", () => filterDocumentationTree(search.value));
  }

  function setupRandomModule() {
    const button = query('[data-action="random-module"]');
    if (!button || !Array.isArray(window.DOCS_MANIFEST) || !window.DOCS_MANIFEST.length) return;
    button.addEventListener("click", () => {
      const documentRecord = window.DOCS_MANIFEST[Math.floor(Math.random() * window.DOCS_MANIFEST.length)];
      const headings = documentRecord.headings || [];
      const targetHeading = headings[Math.floor(Math.random() * Math.max(1, headings.length))] || "";
      const headingTitle = typeof targetHeading === "string" ? targetHeading : targetHeading.title || "";
      const slug = typeof targetHeading === "object" && targetHeading.slug
        ? targetHeading.slug
        : headingTitle
          .toLowerCase()
          .replace(/<[^>]+>/g, "")
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-|-$/g, "");
      window.location.href = `${documentRecord.html}${slug ? `#${slug}` : ""}`;
    });
  }

  function setupTocSearch() {
    const input = query("#toc-search");
    if (!input) return;
    input.addEventListener("input", () => {
      const term = input.value.trim().toLowerCase();
      queryAll(".toc-list li").forEach((item) => {
        item.hidden = Boolean(term) && !item.textContent.toLowerCase().includes(term);
      });
    });
  }

  function setupScrollSpy() {
    const links = queryAll(".toc-list a");
    if (!links.length || !("IntersectionObserver" in window)) return;
    const linkById = new Map(links.map((link) => [link.getAttribute("href").slice(1), link]));
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top)[0];
        if (!visible) return;
        links.forEach((link) => link.classList.remove("is-active"));
        const active = linkById.get(visible.target.id);
        if (active) active.classList.add("is-active");
      },
      { rootMargin: "-18% 0px -68% 0px", threshold: [0, 0.1, 0.4] }
    );
    queryAll(".lesson").forEach((section) => observer.observe(section));
  }

  function diagramNode(svg, label, number, x, y, point, onActivate) {
    const group = makeSvgElement("g", {
      class: "diagram-node",
      tabindex: "0",
      role: "button",
      "aria-label": `${label}: ${point}`
    });
    const rect = makeSvgElement("rect", { x, y, width: 230, height: 84, rx: 3 });
    const numberText = makeSvgElement("text", { x: x + 18, y: y + 28, class: "node-number" });
    numberText.textContent = number;
    const labelText = makeSvgElement("text", { x: x + 18, y: y + 57, class: "node-label" });
    labelText.textContent = label;
    group.append(rect, numberText, labelText);
    const activate = () => onActivate(group, point, label);
    group.addEventListener("click", activate);
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });
    svg.appendChild(group);
    return group;
  }

  function setupSectionDiagrams() {
    const labels = ["CLAIM", "EVIDENCE", "BOUNDARY", "DECISION"];
    const positions = [
      [35, 32],
      [735, 32],
      [35, 220],
      [735, 220]
    ];
    queryAll(".section-diagram").forEach((figure) => {
      const stage = query(".diagram-stage", figure);
      const caption = query("figcaption", figure);
      if (!stage || !caption) return;
      let points;
      try {
        points = JSON.parse(figure.dataset.points || "[]");
      } catch (_error) {
        points = [];
      }
      while (points.length < 4) points.push("Inspect this architecture claim against current evidence.");
      const svg = makeSvgElement("svg", {
        viewBox: "0 0 1000 330",
        role: "img",
        "aria-label": `${figure.dataset.title || "Section"} evidence circuit`
      });

      const edgePaths = [
        "M265 74 C390 74 390 145 500 145",
        "M735 74 C610 74 610 145 500 145",
        "M265 262 C390 262 390 185 500 185",
        "M735 262 C610 262 610 185 500 185"
      ];
      edgePaths.forEach((pathData) => {
        svg.appendChild(makeSvgElement("path", { d: pathData, class: "diagram-edge" }));
      });

      const core = makeSvgElement("rect", { x: 405, y: 120, width: 190, height: 90, rx: 4, class: "diagram-core" });
      const coreLabel = makeSvgElement("text", { x: 440, y: 158, class: "diagram-core-label" });
      coreLabel.textContent = "ARCHITECT";
      const coreSubLabel = makeSvgElement("text", { x: 437, y: 184, class: "diagram-core-label" });
      coreSubLabel.textContent = "JUDGEMENT";
      svg.append(core, coreLabel, coreSubLabel);

      const nodes = [];
      const activateNode = (activeNode, point, label) => {
        nodes.forEach((node) => node.classList.remove("is-active"));
        activeNode.classList.add("is-active");
        caption.textContent = `${label}: ${point}`;
      };
      labels.forEach((label, index) => {
        const [x, y] = positions[index];
        nodes.push(diagramNode(svg, label, String(index + 1).padStart(2, "0"), x, y, points[index], activateNode));
      });
      stage.replaceChildren(svg);
    });
  }

  function activateDocumentMap(objectElement) {
    let svgDocument;
    try {
      svgDocument = objectElement.contentDocument;
    } catch (_error) {
      return;
    }
    if (!svgDocument) return;
    const nodes = Array.from(svgDocument.querySelectorAll(".module-node"));
    const activate = (node) => {
      nodes.forEach((item) => item.classList.remove("active"));
      node.classList.add("active");
      const target = document.getElementById(node.dataset.target || "");
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        history.replaceState(null, "", `#${target.id}`);
      }
    };
    nodes.forEach((node) => {
      node.addEventListener("click", () => activate(node));
      node.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate(node);
        }
      });
    });
  }

  function activateIndexMap(objectElement) {
    let svgDocument;
    try {
      svgDocument = objectElement.contentDocument;
    } catch (_error) {
      return;
    }
    if (!svgDocument) return;
    const nodes = Array.from(svgDocument.querySelectorAll(".category-node"));
    const activate = (node) => {
      const category = node.dataset.category || "";
      const search = query("#docs-search");
      if (search) {
        search.value = category;
        filterDocumentationTree(category);
        query("#documentation-tree")?.scrollIntoView({ behavior: "smooth" });
      }
    };
    nodes.forEach((node) => {
      node.addEventListener("click", () => activate(node));
      node.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate(node);
        }
      });
    });
  }

  function setupGovernedLoop() {
    const objectElement = query("object.governed-loop-map");
    const cards = queryAll(".loop-system-card");
    const consoleElement = query(".loop-console");
    if (!objectElement && !cards.length) return;
    let svgNodes = [];

    const activate = (system, detail) => {
      cards.forEach((card) => card.classList.toggle("is-active", card.dataset.loopSystem === system));
      svgNodes.forEach((node) => node.classList.toggle("active", node.dataset.system === system));
      if (consoleElement) {
        consoleElement.textContent = `${system.toUpperCase()} :: ${detail}`;
      }
    };

    cards.forEach((card) => {
      const system = card.dataset.loopSystem || "system";
      const detail = query("p", card)?.textContent.trim() || "Inspect this governed-loop responsibility.";
      const select = () => activate(system, detail);
      card.addEventListener("click", select);
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });
    });

    if (!objectElement) return;
    objectElement.addEventListener("load", () => {
      const svgDocument = objectElement.contentDocument;
      if (!svgDocument) return;
      svgNodes = Array.from(svgDocument.querySelectorAll(".loop-node"));
      svgNodes.forEach((node) => {
        const select = () => activate(
          node.dataset.system || "system",
          node.dataset.detail || "Inspect this governed-loop responsibility."
        );
        node.addEventListener("click", select);
        node.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            select();
          }
        });
      });
    });
  }

  function setupConceptMaps() {
    queryAll("object.concept-map").forEach((objectElement) => {
      objectElement.addEventListener("load", () => {
        const svgDocument = objectElement.contentDocument;
        if (!svgDocument) return;
        const nodes = Array.from(svgDocument.querySelectorAll(".concept-node"));
        const caption = query(".concept-map-caption", objectElement.closest("figure") || document);
        const activate = (node) => {
          nodes.forEach((item) => item.classList.remove("active"));
          node.classList.add("active");
          if (caption) caption.textContent = node.dataset.detail || "Inspect this concept boundary.";
        };
        nodes.forEach((node) => {
          node.addEventListener("click", () => activate(node));
          node.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              activate(node);
            }
          });
        });
      });
    });
  }

  function setupConceptAtlas() {
    const cards = queryAll(".concept-card");
    if (!cards.length) return;
    const search = query("#concept-search");
    const filters = queryAll(".concept-filter");
    const status = query(".concept-search-status");
    const atlasMap = query("object.atlas-map");
    let selectedCategory = "all";
    let atlasNodes = [];

    const render = () => {
      const term = search?.value.trim().toLowerCase() || "";
      let visibleCount = 0;
      cards.forEach((card) => {
        const categoryMatches = selectedCategory === "all" || card.dataset.category === selectedCategory;
        const searchMatches = !term || (card.dataset.search || "").includes(term);
        card.hidden = !(categoryMatches && searchMatches);
        if (!card.hidden) visibleCount += 1;
      });
      filters.forEach((button) => {
        button.classList.toggle("is-active", button.dataset.conceptCategory === selectedCategory);
      });
      atlasNodes.forEach((node) => {
        node.classList.toggle("active", node.dataset.category === selectedCategory);
      });
      if (status) {
        const suffix = selectedCategory === "all" ? "" : ` IN ${selectedCategory.toUpperCase()}`;
        status.textContent = `${visibleCount} CONCEPT${visibleCount === 1 ? "" : "S"} ONLINE${suffix}`;
      }
    };

    const selectCategory = (category) => {
      selectedCategory = category || "all";
      render();
      query(".atlas-controls")?.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    filters.forEach((button) => {
      button.addEventListener("click", () => selectCategory(button.dataset.conceptCategory));
    });
    search?.addEventListener("input", render);
    if (atlasMap) {
      atlasMap.addEventListener("load", () => {
        const svgDocument = atlasMap.contentDocument;
        if (!svgDocument) return;
        atlasNodes = Array.from(svgDocument.querySelectorAll(".atlas-category"));
        atlasNodes.forEach((node) => {
          const select = () => selectCategory(node.dataset.category);
          node.addEventListener("click", select);
          node.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              select();
            }
          });
        });
      });
    }
    render();
  }

  function setupExternalSvgMaps() {
    queryAll("object.document-map").forEach((objectElement) => {
      objectElement.addEventListener("load", () => activateDocumentMap(objectElement));
    });
    queryAll("object.index-map").forEach((objectElement) => {
      objectElement.addEventListener("load", () => activateIndexMap(objectElement));
    });
  }

  function characterMarkup(palette) {
    return `
      <svg viewBox="0 0 72 92" role="presentation">
        <rect x="18" y="4" width="36" height="8" fill="${palette.hair}" />
        <rect x="12" y="12" width="48" height="36" fill="${palette.skin}" stroke="#2a0648" stroke-width="4" />
        <rect x="18" y="20" width="10" height="10" fill="#ffffff" />
        <rect x="44" y="20" width="10" height="10" fill="#ffffff" />
        <rect class="pixel-eye left-eye" x="22" y="23" width="4" height="4" fill="#2a0648" />
        <rect class="pixel-eye right-eye" x="46" y="23" width="4" height="4" fill="#2a0648" />
        <rect x="28" y="38" width="16" height="4" fill="#a32176" />
        <rect x="9" y="50" width="54" height="30" fill="${palette.suit}" stroke="#2a0648" stroke-width="4" />
        <rect x="30" y="50" width="12" height="24" fill="${palette.tie}" />
        <rect x="4" y="56" width="8" height="24" fill="${palette.skin}" stroke="#2a0648" stroke-width="3" />
        <rect x="60" y="56" width="8" height="24" fill="${palette.skin}" stroke="#2a0648" stroke-width="3" />
        <rect x="14" y="80" width="18" height="8" fill="#2a0648" />
        <rect x="40" y="80" width="18" height="8" fill="#2a0648" />
      </svg>`;
  }

  function setupPixelCrew() {
    const crew = query(".pixel-crew");
    if (!crew || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const palettes = [
      { hair: "#582180", skin: "#f5d7ff", suit: "#7423af", tie: "#39e7ff" },
      { hair: "#ff2fc3", skin: "#fff0fa", suit: "#39105f", tie: "#fff36a" }
    ];
    palettes.forEach((palette, index) => {
      const character = document.createElement("div");
      character.className = "pixel-architect";
      character.dataset.character = String(index);
      character.innerHTML = characterMarkup(palette);
      crew.appendChild(character);
    });

    let lastBubbleAt = 0;
    let lastMoveAt = 0;
    const showThought = (x, y) => {
      const now = Date.now();
      if (now - lastBubbleAt < 1200) return;
      lastBubbleAt = now;
      const bubble = document.createElement("div");
      bubble.className = "thought-bubble";
      bubble.textContent = thoughtMessages[Math.floor(Math.random() * thoughtMessages.length)];
      const left = Math.min(window.innerWidth - 300, Math.max(16, x - 150));
      const top = Math.min(window.innerHeight - 130, Math.max(16, y - 100));
      bubble.style.left = `${left}px`;
      bubble.style.top = `${top}px`;
      document.body.appendChild(bubble);
      window.setTimeout(() => bubble.remove(), 2900);
    };

    window.addEventListener(
      "mousemove",
      (event) => {
        const now = performance.now();
        if (now - lastMoveAt < 90) return;
        lastMoveAt = now;
        const eyeX = Math.max(-2, Math.min(2, (event.clientX / window.innerWidth - 0.5) * 5));
        const eyeY = Math.max(-1, Math.min(1, (event.clientY / window.innerHeight - 0.5) * 3));
        queryAll(".pixel-eye", crew).forEach((eye) => {
          eye.style.transform = `translate(${eyeX}px, ${eyeY}px)`;
        });
        if (Math.random() < 0.075) showThought(event.clientX, event.clientY);
      },
      { passive: true }
    );
  }

  function setupKeyboardShortcuts() {
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && document.body.classList.contains("focus-mode")) {
        document.body.classList.remove("focus-mode");
        sessionStorage.setItem("ourd-docs-focus", "false");
        setButtonState(query('[data-action="focus-mode"]'), false, "EXIT FOCUS", "FOCUS");
      }
    });
  }

  function initialize() {
    setupFocusMode();
    setupEvidenceToggle();
    setupReadingProgress();
    setupTreeToggles();
    setupIndexSearch();
    setupRandomModule();
    setupTocSearch();
    setupScrollSpy();
    setupSectionDiagrams();
    setupExternalSvgMaps();
    setupGovernedLoop();
    setupConceptMaps();
    setupConceptAtlas();
    setupPixelCrew();
    setupKeyboardShortcuts();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
