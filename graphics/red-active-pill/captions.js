// The word being spoken sits in a rounded pill; every other word is plain white with a thin outline.
// Word starts come from the kit's timeline; a word's pill ends when the next word starts or its caption ends.
const all = captions.flatMap(c => {
  const clip = c.el.closest('[data-start][data-duration]');
  const clipEnd = Number(clip.dataset.start) + Number(clip.dataset.duration);
  return c.words.map(w => ({...w, end: Number.isFinite(w.end) ? w.end : clipEnd}));
}).sort((a, b) => a.at - b.at);
all.forEach((w, i) => {
  const next = all[i + 1];
  if (!(Number.isFinite(w.at) && Number.isFinite(w.end) && w.end > w.at)) return;
  tl.set(w.el, {backgroundColor: style.highlight_color || '#C61D3A', color: '#FFFFFF', webkitTextStrokeWidth: '0px'}, w.at);
  const end = Math.min(next ? next.at : Infinity, w.end);
  tl.set(w.el, {backgroundColor: 'transparent', webkitTextStrokeWidth: (2 * (style.stroke ?? 1) * scale) + 'px'}, end);
});
