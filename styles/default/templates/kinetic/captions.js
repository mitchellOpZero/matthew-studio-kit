var gold = style.highlight_color || "#E4B15A";
var cream = style.color || "#F6F1E8";
captions.forEach(function (c) {
  c.words.forEach(function (w, i) {
    var enter = c.t0 + i * 0.06;
    tl.fromTo(w.el, { y: 46, opacity: 0 }, { y: 0, opacity: 1, duration: 0.34, ease: "power3.out" }, enter);
    if (!w.hot) return;
    tl.fromTo(w.el, { color: cream, scale: 1 }, { color: gold, scale: 1.08, duration: 0.18, ease: "power2.out" }, w.at);
    var rule = document.createElement("span");
    rule.className = "rule";
    rule.style.color = gold;
    w.el.appendChild(rule);
    tl.fromTo(rule, { scaleX: 0 }, { scaleX: 1, duration: 0.26, ease: "power3.inOut" }, w.at);
  });
});
