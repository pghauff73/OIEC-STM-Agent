(function () {
  "use strict";

  document.documentElement.classList.add("js");

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
  let relationalExplorerController = null;

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

  function setupRelationalSymbolInspector(preview) {
    if (!preview) return;
    const activatePreview = () => {
      const svgDocument = preview.contentDocument;
      if (!svgDocument) return;
      svgDocument.documentElement.dataset.active = "true";
    };
    preview.addEventListener("load", activatePreview);
    if (preview.contentDocument) activatePreview();
  }

  function renderRelationalRelations(selectedObject, objectsById, childrenByParent) {
    const container = query("[data-inspector-relations]");
    if (!container) return;
    const ports = [];
    if (selectedObject.parent_id && objectsById.has(selectedObject.parent_id)) {
      ports.push({
        direction: "PARENT",
        object: objectsById.get(selectedObject.parent_id)
      });
    }
    (childrenByParent.get(selectedObject.object_id) || []).forEach((childObject) => {
      ports.push({ direction: "CHILD", object: childObject });
    });
    (selectedObject.related_ids || []).forEach((relatedId) => {
      if (objectsById.has(relatedId)) {
        ports.push({ direction: "RELATED", object: objectsById.get(relatedId) });
      }
    });
    container.replaceChildren();
    if (!ports.length) {
      const empty = document.createElement("p");
      empty.textContent = "NO ADDITIONAL RELATION PORTS";
      container.appendChild(empty);
      return;
    }
    ports.slice(0, 18).forEach((port) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "relation-port";
      button.dataset.relationalSelect = port.object.object_id;
      const direction = document.createElement("span");
      direction.textContent = port.direction;
      const title = document.createElement("strong");
      title.textContent = port.object.title;
      button.append(direction, title);
      button.addEventListener("click", () => {
        relationalExplorerController?.selectObject(port.object.object_id, true);
      });
      container.appendChild(button);
    });
  }

  function setupRelationalObjectExplorer() {
    const explorer = query(".relational-explorer");
    const records = Array.isArray(window.RELATIONAL_OBJECTS) ? window.RELATIONAL_OBJECTS : [];
    if (!explorer || !records.length) return;

    const objectsById = new Map(records.map((record) => [record.object_id, record]));
    const childrenByParent = new Map();
    records.forEach((record) => {
      if (!childrenByParent.has(record.parent_id)) childrenByParent.set(record.parent_id, []);
      childrenByParent.get(record.parent_id).push(record);
    });
    childrenByParent.forEach((children) => {
      children.sort((left, right) => left.title.localeCompare(right.title));
    });

    const nodes = queryAll("[data-relational-object]", explorer).filter((node) =>
      node.classList.contains("relational-node")
    );
    const nodeById = new Map(nodes.map((node) => [node.dataset.relationalObject, node]));
    const search = query("#relational-search", explorer);
    const filters = queryAll("[data-relational-filter]", explorer);
    const status = query(".relational-search-status", explorer);
    const preview = query("#relational-symbol-preview", explorer);
    const inspectorTitle = query("[data-inspector-title]", explorer);
    const inspectorDescription = query("[data-inspector-description]", explorer);
    const inspectorId = query("[data-inspector-id]", explorer);
    const inspectorKind = query("[data-inspector-kind]", explorer);
    const inspectorRelation = query("[data-inspector-relation]", explorer);
    const inspectorSource = query("[data-inspector-source]", explorer);
    const inspectorOpen = query("[data-inspector-open]", explorer);
    let activeKind = "all";
    let selectedId = records.find((record) => record.kind === "root")?.object_id || records[0].object_id;

    const ancestorsFor = (objectId) => {
      const ancestors = new Set();
      let current = objectsById.get(objectId);
      while (current?.parent_id && objectsById.has(current.parent_id)) {
        ancestors.add(current.parent_id);
        current = objectsById.get(current.parent_id);
      }
      return ancestors;
    };

    const relationIdsFor = (record) => {
      const relationIds = new Set(record.related_ids || []);
      if (record.parent_id) relationIds.add(record.parent_id);
      (childrenByParent.get(record.object_id) || []).forEach((childObject) => {
        relationIds.add(childObject.object_id);
      });
      return relationIds;
    };

    const expandAncestors = (objectId) => {
      ancestorsFor(objectId).forEach((ancestorId) => {
        const ancestorNode = nodeById.get(ancestorId);
        if (!ancestorNode?.classList.contains("relational-branch")) return;
        ancestorNode.classList.add("is-expanded");
        const button = query(".relational-select", ancestorNode);
        button?.setAttribute("aria-expanded", "true");
      });
    };

    const updateInspector = (record) => {
      if (inspectorTitle) inspectorTitle.textContent = record.title;
      if (inspectorDescription) inspectorDescription.textContent = record.description;
      if (inspectorId) inspectorId.textContent = record.object_id;
      if (inspectorKind) inspectorKind.textContent = record.kind.toUpperCase();
      if (inspectorRelation) inspectorRelation.textContent = record.relation;
      if (inspectorSource) inspectorSource.textContent = record.source_key;
      if (inspectorOpen) inspectorOpen.href = record.href;
      if (preview) {
        preview.removeAttribute("data");
        preview.data = record.symbol;
        const fallback = query("a", preview);
        if (fallback) {
          fallback.href = record.symbol;
          fallback.textContent = `Open ${record.title} symbol`;
        }
      }
      renderRelationalRelations(record, objectsById, childrenByParent);
    };

    const selectObject = (objectId, scrollToNode = false) => {
      const record = objectsById.get(objectId);
      if (!record) return;
      selectedId = objectId;
      const relationIds = relationIdsFor(record);
      nodes.forEach((node) => {
        const nodeId = node.dataset.relationalObject;
        node.classList.toggle("is-selected", nodeId === objectId);
        node.classList.toggle("is-related", relationIds.has(nodeId));
      });
      expandAncestors(objectId);
      updateInspector(record);
      if (scrollToNode) {
        const targetNode = nodeById.get(objectId);
        if (targetNode) targetNode.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    };

    const render = () => {
      const term = search?.value.trim().toLowerCase() || "";
      const directMatches = new Set();
      records.forEach((record) => {
        const kindMatches = activeKind === "all" || record.kind === activeKind;
        const haystack = `${record.title} ${record.description} ${record.kind} ${record.relation} ${record.source_key}`.toLowerCase();
        if (kindMatches && (!term || haystack.includes(term))) directMatches.add(record.object_id);
      });
      const visibleIds = new Set(directMatches);
      directMatches.forEach((objectId) => {
        ancestorsFor(objectId).forEach((ancestorId) => visibleIds.add(ancestorId));
      });
      nodes.forEach((node) => {
        node.hidden = !visibleIds.has(node.dataset.relationalObject);
      });
      queryAll(".relational-tree-zone", explorer).forEach((zone) => {
        zone.hidden = !queryAll(".relational-node", zone).some((node) => !node.hidden);
      });
      if (term || activeKind !== "all") {
        visibleIds.forEach((objectId) => expandAncestors(objectId));
        const conceptZone = query(".relational-concept-zone", explorer);
        if (conceptZone && queryAll('.relational-node[data-relational-kind="concept"]', conceptZone).some((node) => !node.hidden)) {
          conceptZone.open = true;
        }
      }
      filters.forEach((button) => {
        button.setAttribute("aria-pressed", button.dataset.relationalFilter === activeKind ? "true" : "false");
      });
      if (status) {
        const suffix = activeKind === "all" ? "" : ` / ${activeKind.toUpperCase()}`;
        status.textContent = `${directMatches.size} OBJECT${directMatches.size === 1 ? "" : "S"} ONLINE${suffix}`;
      }
    };

    const applyFilter = (kind) => {
      activeKind = objectsById.size && (kind === "all" || records.some((record) => record.kind === kind)) ? kind : "all";
      render();
      explorer.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    relationalExplorerController = { selectObject, applyFilter, render };
    queryAll("[data-relational-select]", explorer).forEach((button) => {
      button.addEventListener("click", () => {
        const objectId = button.dataset.relationalSelect;
        const node = nodeById.get(objectId);
        if (node?.classList.contains("relational-branch")) {
          const expanded = node.classList.toggle("is-expanded");
          button.setAttribute("aria-expanded", expanded ? "true" : "false");
        }
        selectObject(objectId);
      });
    });
    filters.forEach((button) => {
      button.addEventListener("click", () => applyFilter(button.dataset.relationalFilter));
    });
    search?.addEventListener("input", render);
    queryAll("[data-relational-jump]").forEach((button) => {
      button.addEventListener("click", () => {
        activeKind = "all";
        if (search) search.value = "";
        render();
        selectObject(button.dataset.relationalJump, true);
      });
    });
    window.addEventListener("relational-filter-request", (event) => {
      applyFilter(event.detail?.kind || "all");
    });
    setupRelationalSymbolInspector(preview);
    render();
    selectObject(selectedId);
  }

  function setupRelationalTopology() {
    const topologyMap = query("object.relational-topology-map");
    if (!topologyMap) return;
    const activateTopology = () => {
      const svgDocument = topologyMap.contentDocument;
      if (!svgDocument) return;
      const kindNodes = Array.from(svgDocument.querySelectorAll("[data-relational-kind]"));
      const activateKind = (kindNode) => {
        kindNodes.forEach((node) => node.classList.toggle("active", node === kindNode));
        window.dispatchEvent(
          new CustomEvent("relational-filter-request", {
            detail: { kind: kindNode.dataset.relationalKind || "all" }
          })
        );
      };
      kindNodes.forEach((kindNode) => {
        kindNode.addEventListener("click", () => activateKind(kindNode));
        kindNode.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            activateKind(kindNode);
          }
        });
      });
    };
    topologyMap.addEventListener("load", activateTopology);
    if (topologyMap.contentDocument) activateTopology();
  }

  function setupEssayLogicMaps() {
    queryAll("[data-essay-logic-map]").forEach((map) => {
      const buttons = queryAll("[data-logic-target]", map);
      const paragraphs = buttons
        .map((button) => document.getElementById(button.dataset.logicTarget))
        .filter(Boolean);
      const activate = (targetId, scroll = false) => {
        const activeButton = buttons.find((button) => button.dataset.logicTarget === targetId);
        const activeOrder = Number(activeButton?.dataset.logicOrder || 0);
        map.dataset.activeLogicNode = activeButton?.dataset.logicNode || "";
        buttons.forEach((button) => {
          const active = button.dataset.logicTarget === targetId;
          const complete = Number(button.dataset.logicOrder || 0) < activeOrder;
          button.classList.toggle("is-active", active);
          button.classList.toggle("is-logic-complete", complete);
          button.setAttribute("aria-pressed", active ? "true" : "false");
          if (active) button.setAttribute("aria-current", "step");
          else button.removeAttribute("aria-current");
        });
        paragraphs.forEach((paragraph) => {
          const complete = Number(paragraph.dataset.logicOrder || 0) < activeOrder;
          paragraph.classList.toggle("is-logic-active", paragraph.id === targetId);
          paragraph.classList.toggle("is-logic-complete", complete);
        });
        const target = document.getElementById(targetId);
        if (scroll && target) {
          target.scrollIntoView({ behavior: "smooth", block: "center" });
          target.focus({ preventScroll: true });
        }
      };
      buttons.forEach((button) => {
        button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", () => activate(button.dataset.logicTarget, true));
        button.addEventListener("focus", () => activate(button.dataset.logicTarget));
      });
      paragraphs.forEach((paragraph) => {
        paragraph.tabIndex = 0;
        paragraph.addEventListener("focus", () => activate(paragraph.id));
      });
    });
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
      const target = event.target;
      const isTyping = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;
      if (event.key === "/" && !isTyping) {
        const relationalSearch = query("#relational-search");
        if (relationalSearch) {
          event.preventDefault();
          relationalSearch.focus();
        }
      }
      if (event.key === "Escape" && document.body.classList.contains("focus-mode")) {
        document.body.classList.remove("focus-mode");
        sessionStorage.setItem("ourd-docs-focus", "false");
        setButtonState(query('[data-action="focus-mode"]'), false, "EXIT FOCUS", "FOCUS");
      }
    });
  }

  function readJsonScript(selector, fallback, root = document) {
    const element = query(selector, root);
    if (!element) return fallback;
    try {
      return JSON.parse(element.textContent || "");
    } catch (_error) {
      return fallback;
    }
  }

  function safeLocalGet(key, fallback = "") {
    try {
      return window.localStorage.getItem(key) ?? fallback;
    } catch (_error) {
      return fallback;
    }
  }

  function safeLocalSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (_error) {
      return;
    }
  }

  function setupDocumentationViews() {
    const buttons = queryAll("[data-doc-view]");
    const depth = query("[data-depth-control]");
    if (!buttons.length && !depth) return;

    const allowedViews = new Set(["learn", "technical"]);
    const savedView = safeLocalGet("oiec-docs-view", "learn");
    const initialView = allowedViews.has(savedView) ? savedView : "learn";
    document.documentElement.dataset.docView = initialView;

    const applyView = (view) => {
      const selected = allowedViews.has(view) ? view : "learn";
      document.documentElement.dataset.docView = selected;
      safeLocalSet("oiec-docs-view", selected);
      buttons.forEach((button) => {
        button.setAttribute("aria-pressed", button.dataset.docView === selected ? "true" : "false");
      });
    };

    buttons.forEach((button) => button.addEventListener("click", () => applyView(button.dataset.docView)));
    applyView(initialView);

    if (depth) {
      const depthNames = ["novice", "intermediate", "expert"];
      const savedDepth = Number.parseInt(safeLocalGet("oiec-docs-depth", "0"), 10);
      const initialDepth = Number.isInteger(savedDepth) ? Math.min(2, Math.max(0, savedDepth)) : 0;
      const applyDepth = (value) => {
        const bounded = Math.min(2, Math.max(0, Number.parseInt(String(value), 10) || 0));
        depth.value = String(bounded);
        document.documentElement.dataset.docDepth = depthNames[bounded];
        safeLocalSet("oiec-docs-depth", String(bounded));
      };
      depth.addEventListener("input", () => applyDepth(depth.value));
      applyDepth(initialDepth);
    }
  }

  function setupTeacherMode() {
    const button = query('[data-action="teacher-mode"]');
    if (!button) return;
    const panels = queryAll("[data-teacher-content]");
    const apply = (enabled) => {
      panels.forEach((panel) => {
        panel.hidden = !enabled;
      });
      button.setAttribute("aria-pressed", enabled ? "true" : "false");
      button.textContent = enabled ? "Exit teacher mode" : "Teacher mode";
      safeLocalSet("oiec-docs-teacher", enabled ? "true" : "false");
    };
    apply(safeLocalGet("oiec-docs-teacher", "false") === "true");
    button.addEventListener("click", () => apply(button.getAttribute("aria-pressed") !== "true"));
  }

  function setupLearningReset() {
    const button = query('[data-action="reset-learning"]');
    if (!button) return;
    button.addEventListener("click", () => {
      try {
        Object.keys(window.localStorage)
          .filter((key) => key.startsWith("oiec-docs-"))
          .forEach((key) => window.localStorage.removeItem(key));
      } catch (_error) {
        return;
      }
      document.documentElement.dataset.docView = "learn";
      document.documentElement.dataset.docDepth = "novice";
      window.location.reload();
    });
  }

  function setupVocabularyMemory() {
    const conceptId = document.body.dataset.concept;
    const lead = query(".concept-teaching .lead");
    if (!conceptId || !lead) return;
    const key = `oiec-docs-vocab-${conceptId}`;
    const count = Number.parseInt(safeLocalGet(key, "0"), 10) || 0;
    const nextCount = Math.min(99, count + 1);
    safeLocalSet(key, String(nextCount));
    if (nextCount < 3) return;
    const fullText = lead.textContent || "";
    const firstSentence = fullText.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim();
    if (firstSentence && firstSentence.length < fullText.length) {
      lead.textContent = firstSentence;
    }
    const marker = document.createElement("p");
    marker.className = "vocabulary-familiar";
    marker.textContent = `Familiar term · concise explanation after ${nextCount} local views`;
    lead.insertAdjacentElement("afterend", marker);
  }

  function stemIntentToken(token) {
    return token
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "")
      .replace(/(?:ing|ed|es|s)$/g, "");
  }

  function setupIntentSearch() {
    const input = query("#intent-search");
    if (!input) return;
    const cards = queryAll(".task-card");
    const status = query("[data-intent-status]");
    const ignored = new Set(["a", "an", "the", "i", "want", "to", "my", "agent"]);
    const update = () => {
      const tokens = input.value
        .split(/\s+/)
        .map(stemIntentToken)
        .filter((token) => token && !ignored.has(token));
      let visible = 0;
      cards.forEach((card) => {
        const haystack = stemIntentToken(`${card.textContent || ""} ${card.dataset.intentTerms || ""}`);
        const matches = !tokens.length || tokens.some((token) => haystack.includes(token));
        card.hidden = !matches;
        if (matches) visible += 1;
      });
      if (status) {
        status.textContent = tokens.length
          ? `${visible} task route${visible === 1 ? "" : "s"} matched. Failure and repeated-action searches lead to CFEL and failure memory.`
          : `${cards.length} task routes available`;
      }
    };
    input.addEventListener("input", update);
    update();
  }

  function setupTutorialSandboxes() {
    queryAll("[data-tutorial-sandbox]").forEach((sandbox) => {
      const fixture = readJsonScript("[data-sandbox-fixture]", {}, sandbox);
      const output = query(".sandbox-output", sandbox);
      const run = query("[data-sandbox-run]", sandbox);
      const reset = query("[data-sandbox-reset]", sandbox);
      if (!output || !run || !reset) return;
      const states = Array.isArray(fixture.states)
        ? fixture.states.map(String)
        : [
            `Refused: ${String(fixture.violated_invariant || "The selected action violates a declared invariant.")}`,
            `Evidence needed: ${String(fixture.required_evidence || "Additional evidence is required.")}`
          ];
      let index = 0;
      const renderNext = () => {
        if (index >= states.length) return;
        const item = document.createElement("li");
        item.textContent = states[index];
        output.appendChild(item);
        index += 1;
        run.disabled = index >= states.length;
      };
      reset.addEventListener("click", () => {
        index = 0;
        output.replaceChildren();
        run.disabled = false;
      });
      run.addEventListener("click", renderNext);
    });
  }

  function setupCommandCopy() {
    queryAll("[data-copy-command]").forEach((button) => {
      button.addEventListener("click", async () => {
        const command = query("pre code", button.closest(".command-card"));
        if (!command) return;
        try {
          await navigator.clipboard.writeText(command.textContent || "");
          button.textContent = "Copied";
        } catch (_error) {
          button.textContent = "Select command text to copy";
        }
      });
    });
  }

  function setupAcronymInspector() {
    const button = query('[data-action="inspect-acronyms"]');
    const input = query("#acronym-input");
    const output = query("[data-acronym-output]");
    if (!button || !input || !output) return;
    const catalog = readJsonScript("#acronym-catalog", {});
    const inspect = () => {
      output.replaceChildren();
      const tokens = Array.from(new Set((input.value.match(/\b[A-Z][A-Z0-9-]{1,}\b/g) || [])));
      if (!tokens.length) {
        output.textContent = "No uppercase acronym-like tokens found.";
        return;
      }
      const list = document.createElement("dl");
      tokens.forEach((token) => {
        const term = document.createElement("dt");
        term.textContent = token;
        const definition = document.createElement("dd");
        definition.textContent = Object.prototype.hasOwnProperty.call(catalog, token)
          ? String(catalog[token])
          : "Unresolved: the canonical acronym catalog does not define this token.";
        list.append(term, definition);
      });
      output.appendChild(list);
    };
    button.addEventListener("click", inspect);
    inspect();
  }

  function setupStatusDecoder() {
    const button = query('[data-action="decode-status"]');
    const input = query("#status-input");
    const output = query("[data-status-output]");
    if (!button || !input || !output) return;
    const catalog = readJsonScript("#status-catalog", {});
    const decode = () => {
      const key = input.value.trim().toUpperCase();
      output.replaceChildren();
      const record = catalog[key];
      if (!record) {
        output.textContent = "Unknown status. No meaning is guessed; inspect the source or update the canonical catalog.";
        return;
      }
      const heading = document.createElement("h2");
      heading.textContent = key;
      const fields = [
        ["Plain English", record.plain_language_meaning],
        ["Trigger", record.trigger],
        ["What happens next", record.what_happens_next],
        ["User action", record.user_action],
        ["Sources", Array.isArray(record.source_paths) ? record.source_paths.join(", ") : ""]
      ];
      const list = document.createElement("dl");
      fields.forEach(([label, value]) => {
        const term = document.createElement("dt");
        term.textContent = label;
        const definition = document.createElement("dd");
        definition.textContent = String(value || "Not declared");
        list.append(term, definition);
      });
      output.append(heading, list);
    };
    button.addEventListener("click", decode);
    decode();
  }

  function shellQuote(value) {
    if (/^[A-Za-z0-9_./:@-]+$/.test(value)) return value;
    return `'${value.replace(/'/g, `'"'"'`)}'`;
  }

  function setupCommandBuilder() {
    const button = query('[data-action="build-command"]');
    const selector = query("[data-builder-program]");
    const output = query("[data-command-output]");
    const explanation = query("[data-command-explanation]");
    if (!button || !selector || !output || !explanation) return;
    const recipes = readJsonScript("#command-recipes", []);
    const byId = new Map(recipes.map((recipe) => [recipe.command_id, recipe]));
    const build = () => {
      const recipe = byId.get(selector.value);
      if (!recipe) {
        output.textContent = "";
        explanation.textContent = "Unknown command recipe.";
        return;
      }
      const workspace = query("[data-builder-workspace]")?.value.trim() || ".";
      const target = query("[data-builder-target]")?.value.trim() || "src/parser.py";
      const risk = query("[data-builder-risk]")?.value || "L0";
      const argv = Array.from(recipe.argv, String);
      argv.forEach((token, index) => {
        if ((argv[index - 1] === "--repo" || index === 1 && recipe.program_id === "agent") && token === ".") argv[index] = workspace;
        if (token.includes("src/parser.py")) argv[index] = token.replace("src/parser.py", target);
        if (argv[index - 1] === "--risk") argv[index] = risk;
      });
      output.textContent = argv.map(shellQuote).join(" ");
      explanation.replaceChildren();
      const title = document.createElement("strong");
      title.textContent = String(recipe.title);
      const text = document.createElement("p");
      text.textContent = `${String(recipe.purpose)} This command is generated from parser-validated checked-in tokens; it is not executed by the browser.`;
      explanation.append(title, text);
    };
    button.addEventListener("click", build);
    selector.addEventListener("change", build);
    build();
  }

  function setupProviderWizard() {
    const button = query('[data-action="show-provider-recipe"]');
    const selector = query("[data-provider-choice]");
    const output = query("[data-provider-output]");
    if (!button || !selector || !output) return;
    const recipes = readJsonScript("#command-recipes", []);
    const byId = new Map(recipes.map((recipe) => [recipe.command_id, recipe]));
    const show = () => {
      const recipe = byId.get(selector.value);
      output.textContent = recipe ? Array.from(recipe.argv, String).map(shellQuote).join(" ") : "No checked-in provider recipe is available.";
    };
    button.addEventListener("click", show);
    selector.addEventListener("change", show);
    show();
  }

  function setupSharedSvgCards() {
    queryAll("object.learning-diagram, .learning-diagram object, .novice-hero object").forEach((objectElement) => {
      objectElement.addEventListener("load", () => {
        const svgDocument = objectElement.contentDocument;
        if (!svgDocument) return;
        svgDocument.querySelectorAll("[data-doc-node]").forEach((node) => {
          const describe = () => {
            const figure = objectElement.closest("figure");
            const caption = figure ? query("figcaption", figure) : null;
            if (!caption) return;
            const label = node.getAttribute("aria-label") || node.getAttribute("data-doc-node") || "Diagram node";
            const role = node.getAttribute("data-node-role") || "concept";
            caption.textContent = `${label} · visual role: ${role}. Follow the page explanation for inputs, outputs, evidence, and related concepts.`;
          };
          node.addEventListener("click", describe);
          node.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              describe();
            }
          });
        });
      });
    });
  }

  function initialize() {
    setupDocumentationViews();
    setupTeacherMode();
    setupLearningReset();
    setupVocabularyMemory();
    setupIntentSearch();
    setupTutorialSandboxes();
    setupCommandCopy();
    setupAcronymInspector();
    setupStatusDecoder();
    setupCommandBuilder();
    setupProviderWizard();
    setupSharedSvgCards();
    setupFocusMode();
    setupEvidenceToggle();
    setupReadingProgress();
    setupTreeToggles();
    setupIndexSearch();
    setupRelationalObjectExplorer();
    setupRelationalTopology();
    setupEssayLogicMaps();
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
