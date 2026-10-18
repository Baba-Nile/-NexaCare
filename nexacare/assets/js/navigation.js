(function () {
  var header = document.querySelector('.site-header');
  if (header) {
    var onScroll = function () { header.classList.toggle('is-scrolled', window.scrollY > 8); };
    window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
  }
  var btn = document.querySelector('.nav-toggle'), nav = document.getElementById('site-nav');
  if (!btn || !nav) return;
  function closeSubs() {
    nav.querySelectorAll('.has-sub').forEach(function (li) {
      li.classList.remove('is-open'); li.querySelector('.sub-toggle').setAttribute('aria-expanded', 'false');
    });
  }
  function closeNav() { nav.classList.remove('is-open'); btn.setAttribute('aria-expanded', 'false'); }
  btn.addEventListener('click', function () {
    var open = nav.classList.toggle('is-open'); btn.setAttribute('aria-expanded', String(open));
  });
  nav.querySelectorAll('.sub-toggle').forEach(function (t) {
    t.addEventListener('click', function () {
      var li = t.parentElement, willOpen = !li.classList.contains('is-open');
      closeSubs(); li.classList.toggle('is-open', willOpen); t.setAttribute('aria-expanded', String(willOpen));
    });
  });
  document.addEventListener('click', function (e) {
    if (!nav.contains(e.target) && !btn.contains(e.target)) { closeSubs(); closeNav(); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { var wasOpen = nav.classList.contains('is-open'); closeSubs(); closeNav(); if (wasOpen) btn.focus(); }
  });
})();
