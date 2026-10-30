// A bar slides in under each keyword as it is spoken (left to right), then holds. Keywords stay white.
var h = (style.underline_thickness_px || 12) * scale, gap = (style.underline_gap_px || 4) * scale;
var slide = (style.underline_slide_ms || 120) / 1000;
captions.forEach(function (c) {
  c.words.forEach(function (w) {
    if (!w.hot) return;
    var ul = document.createElement("span"); ul.className = "ul";
    ul.style.height = h + "px"; ul.style.bottom = (-gap) + "px";
    var bar = document.createElement("i"); bar.style.background = style.highlight_color || "#DC143C";
    ul.appendChild(bar); w.el.appendChild(ul);
    tl.fromTo(bar, {xPercent: -100}, {xPercent: 0, duration: slide, ease: "none"}, w.at);
  });
});
