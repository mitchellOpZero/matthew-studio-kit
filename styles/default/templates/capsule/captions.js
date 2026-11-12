var accent = style.highlight_color || "#8AB4F8";
var ink = style.color || "#F3F4F6";
captions.forEach(function (c) {
  tl.fromTo(c.el, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.16, ease: "power2.out" }, c.t0);
  c.words.forEach(function (w) {
    if (!w.hot) return;
    tl.set(w.el, { color: ink }, c.t0);
    tl.to(w.el, { color: accent, duration: 0.12, ease: "none" }, w.at);
  });
});
