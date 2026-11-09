// Branch features: home-page branch picker, branch search and filters, ?branch= pre-selection, and appointment branch chips.
(function () {
  // 1. Home page "Find your nearest branch" bar: go straight to the chosen branch.
  document.querySelectorAll('[data-branch-finder]').forEach(function (f) {
    var sel = f.querySelector('select');
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!sel.value) { sel.setAttribute('aria-invalid', 'true'); sel.focus(); return; }
      window.location.href = sel.value;
    });
    sel.addEventListener('change', function () { sel.removeAttribute('aria-invalid'); });
  });

  // 2. Branch search and filters on the Our Branches page. Only text the page already shows is searched.
  var finder = document.querySelector('[data-finder]');
  if (finder) {
    var cards = Array.prototype.slice.call(document.querySelectorAll('[data-branch]'));
    var input = finder.querySelector('input[type=search]'), clear = finder.querySelector('.finder__clear'), count = finder.querySelector('.finder__count');
    var empty = document.querySelector('[data-empty]'), boxes = finder.querySelectorAll('[data-filter]');
    var run = function () {
      var q = input.value.trim().toLowerCase(), words = q ? q.split(/\s+/) : [], shown = 0;
      cards.forEach(function (c) {
        var hay = c.getAttribute('data-search') || '';
        var ok = words.every(function (w) { return hay.indexOf(w) !== -1; });
        boxes.forEach(function (b) { if (b.checked && !c.hasAttribute('data-has-' + b.getAttribute('data-filter'))) ok = false; });
        c.hidden = !ok; if (ok) shown++;
      });
      clear.hidden = !q;
      count.textContent = shown === cards.length ? 'Showing all ' + cards.length + ' locations' : (shown + ' of ' + cards.length + ' locations match');
      if (empty) empty.hidden = shown !== 0;
    };
    input.addEventListener('input', run);
    boxes.forEach(function (b) { b.addEventListener('change', run); });
    clear.addEventListener('click', function () { input.value = ''; run(); input.focus(); });
    run();
  }

  // 3. Pre-select a branch from ?branch=slug (links from branch cards and the contact page).
  var wanted = null;
  try { wanted = new URLSearchParams(window.location.search).get('branch'); } catch (e) {}
  var selects = document.querySelectorAll('form[data-enquiry] select[name=branch]');
  if (wanted) selects.forEach(function (s) {
    for (var i = 0; i < s.options.length; i++) { if (s.options[i].value === wanted) { s.value = wanted; s.dispatchEvent(new Event('change', { bubbles: true })); break; } }
  });

  // 4. Appointment page: branch chips and the branch field stay in step.
  var chips = document.querySelectorAll('[data-pick-branch]'), formSel = document.querySelector('#appointment-form select[name=branch]');
  if (chips.length && formSel) {
    var sync = function () { chips.forEach(function (c) { c.setAttribute('aria-pressed', String(c.getAttribute('data-pick-branch') === formSel.value)); }); };
    chips.forEach(function (c) {
      c.addEventListener('click', function () {
        formSel.value = c.getAttribute('data-pick-branch'); formSel.dispatchEvent(new Event('change', { bubbles: true }));
        formSel.removeAttribute('aria-invalid'); var er = document.getElementById(formSel.id + '-err'); if (er) er.remove();
        if (window.matchMedia('(max-width:899px)').matches) document.getElementById('appointment-form').scrollIntoView({ behavior: 'smooth' });
      });
    });
    formSel.addEventListener('change', sync); sync();
  }
})();
