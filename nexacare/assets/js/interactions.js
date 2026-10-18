// Team directory filters: only shown when the directory has enough staff to justify them.
(function () {
  var wrap = document.querySelector('[data-team-filters]'); if (!wrap) return;
  var cards = document.querySelectorAll('[data-staff]'); if (cards.length < 6) return;
  wrap.hidden = false;
  var dept = wrap.querySelector('[name=dept]'), role = wrap.querySelector('[name=role]');
  function fill(sel, key) {
    var vals = {}; cards.forEach(function (c) { if (c.dataset[key]) vals[c.dataset[key]] = 1; });
    Object.keys(vals).sort().forEach(function (v) { var o = document.createElement('option'); o.value = o.textContent = v; sel.appendChild(o); });
  }
  fill(dept, 'dept'); fill(role, 'role');
  function apply() { cards.forEach(function (c) { c.hidden = (dept.value && c.dataset.dept !== dept.value) || (role.value && c.dataset.role !== role.value); }); }
  dept.addEventListener('change', apply); role.addEventListener('change', apply);
})();

// Horizontal carousel (services): scroll-snap track with previous/next buttons.
(function () {
  document.querySelectorAll('[data-carousel]').forEach(function (c) {
    var track = c.querySelector('.carousel__track'); if (!track) return;
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    function go(dir) { track.scrollBy({ left: dir * track.clientWidth * 0.9, behavior: reduce ? 'auto' : 'smooth' }); }
    c.querySelector('[data-prev]').addEventListener('click', function () { go(-1); });
    c.querySelector('[data-next]').addEventListener('click', function () { go(1); });
  });
})();
