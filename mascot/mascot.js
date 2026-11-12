// The banana in each page's header (mascot.css): it hops on every click; enough clicks in a row put its
// sunglasses on, kept in this browser, and as many again take them off. The Konami code anywhere on the page
// sends a short shower of small bananas. The button carries its labels in the page's language and stays
// disabled, a still picture, until this script runs.
// Each easter egg can be switched off on the button, as in the apps: no data-mascot-clicks, or "0", turns the
// sunglasses off (clicks only hop, nothing is saved), and data-mascot-konami="off" turns the Konami code off.
//
// Ported from BananaWiki mascot 14d63ec44444 (bananawiki/core/mascot.py and bananawiki/core/static/mascot/
// in that tree). When those change, BananaWiki's scripts/make_icons.py fails until the change is ported here
// and recorded with its --ported option.
(() => {
  "use strict";

  const STORE_KEY = "bananawiki-site.mascot.shades";
  const KONAMI = ["ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"];
  const SHOWER_SIZE = 10;
  const SHOWER_MS = 3000;
  const SVG_NS = "http://www.w3.org/2000/svg";

  function stillMotion() {
    return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  }

  function remembered() {
    try {
      return window.localStorage.getItem(STORE_KEY) === "1";
    } catch {
      return false;
    }
  }

  function remember(on) {
    try {
      if (on) window.localStorage.setItem(STORE_KEY, "1");
      else window.localStorage.removeItem(STORE_KEY);
    } catch {
      // Storage blocked: the sunglasses stay until the page is left.
    }
  }

  function typing(target) {
    return Boolean(target) && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName || ""));
  }

  function initMascot(button, sprite) {
    const needed = Number.parseInt(button.dataset.mascotClicks, 10);
    const shadesEgg = needed > 0; // false for a missing, empty or "0" count
    const konamiEgg = button.dataset.mascotKonami !== "off";
    const label = button.getAttribute("aria-label") || "";
    const labelShades = button.dataset.labelShades || label;
    const timers = {};
    let clicks = 0;

    // Says "Deal with it." or "Sunglasses off." to screen readers; the sunglasses show it to everyone else.
    const status = document.createElement("span");
    status.className = "visually-hidden";
    status.setAttribute("role", "status");
    document.body.append(status);

    const replay = (className, ms) => {
      clearTimeout(timers[className]); // a click mid-hop restarts it instead of cutting the next one short
      button.classList.remove(className);
      void button.offsetWidth; // restart the animation
      button.classList.add(className);
      timers[className] = setTimeout(() => button.classList.remove(className), ms);
    };

    const wear = (on) => {
      sprite.classList.toggle("mascot-sprite--shades", on);
      button.setAttribute("aria-label", on ? labelShades : label);
      button.setAttribute("title", on ? labelShades : label);
    };

    // The glint is one white art pixel wide and runs across both lenses once they have landed (mascot.css).
    const drop = () => {
      const shades = sprite.querySelector(".mascot__shades");
      if (shades && !shades.querySelector(".mascot__glint")) {
        const glint = document.createElementNS(SVG_NS, "rect");
        const attributes = { class: "mascot__glint", x: 4, y: 6, width: 1, height: 2, fill: "#ffffff" };
        for (const [name, value] of Object.entries(attributes)) glint.setAttribute(name, value);
        shades.append(glint);
      }
      replay("mascot--shades-drop", 950);
    };

    if (shadesEgg && remembered()) wear(true);

    button.addEventListener("click", () => {
      if (!shadesEgg) {
        replay("mascot--hop", 450);
        return;
      }
      clicks += 1;
      // Past half way, the hop gets higher.
      if (clicks * 2 >= needed) button.classList.add("mascot--eager");
      replay("mascot--hop", 450);
      if (clicks < needed) return;
      const on = !sprite.classList.contains("mascot-sprite--shades");
      remember(on);
      wear(on);
      if (on) drop();
      status.textContent = (on ? button.dataset.on : button.dataset.off) || "";
      clicks = 0;
      button.classList.remove("mascot--eager");
    });

    const shower = () => {
      if (document.querySelector(".mascot-shower")) return;
      const layer = document.createElement("div");
      layer.className = "mascot-shower";
      layer.setAttribute("aria-hidden", "true");
      for (let i = 0; i < SHOWER_SIZE; i += 1) {
        const banana = document.createElement("span");
        banana.className = `mascot-shower__banana${i % 3 === 0 ? " mascot-shower__banana--big" : ""}`;
        const copy = sprite.cloneNode(true);
        copy.classList.remove("mascot-sprite--shades");
        banana.append(copy);
        banana.style.left = `${(4 + (i + Math.random()) * 92 / SHOWER_SIZE).toFixed(1)}%`;
        banana.style.animationDelay = `${Math.round(Math.random() * 800)}ms`;
        banana.style.animationDuration = `${1600 + Math.round(Math.random() * 500)}ms`;
        layer.append(banana);
      }
      document.body.append(layer);
      setTimeout(() => layer.remove(), SHOWER_MS);
    };

    button.disabled = false;
    if (!konamiEgg) return;

    let progress = 0;
    document.addEventListener("keydown", (event) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || typing(event.target)) {
        progress = 0;
        return;
      }
      const key = event.key?.length === 1 ? event.key.toLowerCase() : event.key;
      if (key === KONAMI[progress]) progress += 1;
      else if (key === KONAMI[0]) progress = progress === 2 ? 2 : 1;
      else progress = 0;
      if (progress < KONAMI.length) return;
      progress = 0;
      if (stillMotion()) {
        replay("mascot--lean", 600);
      } else {
        replay("mascot--hop", 450);
        shower();
      }
    });
  }

  const button = document.querySelector("[data-mascot]");
  const sprite = button?.querySelector(".mascot-sprite");
  if (sprite) initMascot(button, sprite);
})();
