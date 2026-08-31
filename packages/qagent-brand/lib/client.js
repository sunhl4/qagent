window.__ModuleLoader__.load({
  id: "@qccd/qagent-brand",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    const jsx = require("react/jsx-runtime");

    const PRODUCT = "幺正量子 · Qagent";

    function UnitMark({ size = 24, className }) {
      return jsx.jsxs("svg", {
        width: size,
        height: size,
        viewBox: "0 0 64 64",
        fill: "none",
        className,
        "aria-hidden": "true",
        children: [
          jsx.jsx("rect", { x: 8, y: 14, width: 48, height: 36, rx: 3, stroke: "currentColor", strokeWidth: 1.6 }),
          jsx.jsx("path", { d: "M14 20h36M14 44h36M20 14v36M44 14v36", stroke: "currentColor", strokeWidth: 0.7, opacity: 0.55 }),
          jsx.jsx("circle", { cx: 32, cy: 32, r: 5, fill: "currentColor" }),
          jsx.jsx("circle", { cx: 32, cy: 32, r: 9, stroke: "currentColor", strokeWidth: 1.2 }),
          jsx.jsx("path", { d: "M32 8v6M32 50v6M8 32h6M50 32h6", stroke: "currentColor", strokeWidth: 1.2 }),
        ],
      });
    }

    function UnitName() {
      return jsx.jsxs("span", {
        className: "qagent-wordmark",
        children: [
          jsx.jsx("span", { className: "qagent-wordmark-name", children: "幺正量子" }),
          jsx.jsx("span", { className: "qagent-wordmark-badge", children: "QAGENT" }),
        ],
      });
    }

    function ensureStyle() {
      if (document.querySelector("style[data-plugin-css='qagent-brand']")) return;
      const tag = document.createElement("style");
      tag.dataset.plugin = "@qccd/qagent-brand";
      tag.dataset.pluginCss = "qagent-brand";
      tag.textContent = [
        ".qagent-wordmark{display:inline-flex;align-items:center;gap:8px;height:24px;color:inherit;",
        "font-family:'Source Han Sans SC','PingFang SC','Noto Sans SC','Helvetica Neue',sans-serif}",
        ".qagent-wordmark-name{font-size:14px;font-weight:620;letter-spacing:.04em;line-height:1}",
        ".qagent-wordmark-badge{font-size:10px;font-weight:700;letter-spacing:.08em;line-height:1;",
        "padding:3px 6px;border-radius:2px;background:currentColor;",
        "color:var(--dsw-alias-label-primary-inverted,#071018)}",
      ].join("");
      document.head.appendChild(tag);
    }

    function ensureFavicon() {
      const href = "data:image/svg+xml," + encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">'
        + '<rect x="8" y="14" width="48" height="36" rx="3" stroke="#C9A227" stroke-width="1.6"/>'
        + '<circle cx="32" cy="32" r="5" fill="#E8F2FF"/>'
        + '<circle cx="32" cy="32" r="9" stroke="#C9A227" stroke-width="1.2"/>'
        + '<path d="M32 8v6M32 50v6M8 32h6M50 32h6" stroke="#C9A227" stroke-width="1.2"/>'
        + "</svg>",
      );
      for (const rel of ["icon", "shortcut icon"]) {
        let link = document.querySelector(`link[rel='${rel}']`);
        if (!link) {
          link = document.createElement("link");
          link.rel = rel;
          document.head.appendChild(link);
        }
        link.type = "image/svg+xml";
        link.href = href;
      }
    }

    function retitle() {
      const current = document.title;
      if (!/DeepSeek|DSH|Harness/.test(current)) return;
      const dash = current.lastIndexOf(" — ");
      document.title = dash === -1 ? PRODUCT : `${current.slice(0, dash)} — ${PRODUCT}`;
    }

    const inject = ["slots"];

    function apply(ctx) {
      ensureStyle();
      ensureFavicon();
      retitle();
      ctx.slots.inject("sidebar.brand.mark", () =>
        ctx.slots.inject("sidebar.brand.name", () =>
          ctx.slots.inject("conversation.hero.brand.mark", function* () {
            yield ctx.slots.register({ name: "sidebar.brand.mark", priority: -1 }, UnitMark);
            yield ctx.slots.register({ name: "sidebar.brand.name", priority: -1 }, UnitName);
            yield ctx.slots.register({ name: "conversation.hero.brand.mark", priority: -1 }, UnitMark);
          })));
    }

    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  },
});
