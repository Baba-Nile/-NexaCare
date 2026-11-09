// Main navigation: mobile menu button, sub-menus (hover on desktop via CSS; click, Enter, Space and Escape for touch and keyboard).
(function () {
  var btn = document.querySelector('.nav-toggle'), nav = document.getElementById('site-nav');
  if (!btn || !nav) return;
  var desktop = window.matchMedia('(min-width:1200px)');
  function closeSubs(except) {
    nav.querySelectorAll('.has-sub').forEach(function (li) {
      if (li === except) return;
      li.classList.remove('is-open'); li.querySelector('.sub-toggle').setAttribute('aria-expanded', 'false');
    });
  }
  function closeNav() { nav.classList.remove('is-open'); btn.setAttribute('aria-expanded', 'false'); }
  btn.addEventListener('click', function () {
    var open = nav.classList.toggle('is-open'); btn.setAttribute('aria-expanded', String(open));
    btn.querySelector('i').className = 'fa-solid ' + (open ? 'fa-xmark' : 'fa-bars');
  });
  nav.querySelectorAll('.sub-toggle').forEach(function (t) {
    t.addEventListener('click', function () {
      var li = t.parentElement.parentElement, willOpen = !li.classList.contains('is-open');
      closeSubs(li); li.classList.toggle('is-open', willOpen); t.setAttribute('aria-expanded', String(willOpen));
    });
  });
  // Keep the open state honest when the pointer leaves a desktop menu or focus moves elsewhere.
  nav.querySelectorAll('.has-sub').forEach(function (li) {
    li.addEventListener('focusout', function (e) {
      if (desktop.matches && !li.contains(e.relatedTarget)) { li.classList.remove('is-open'); li.querySelector('.sub-toggle').setAttribute('aria-expanded', 'false'); }
    });
    li.addEventListener('mouseleave', function () {
      if (desktop.matches) { li.classList.remove('is-open'); li.querySelector('.sub-toggle').setAttribute('aria-expanded', 'false'); }
    });
  });
  document.addEventListener('click', function (e) {
    if (!nav.contains(e.target) && !btn.contains(e.target)) { closeSubs(); if (!desktop.matches) closeNav(); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var openSub = nav.querySelector('.has-sub.is-open'), wasOpen = nav.classList.contains('is-open');
    var focusTo = openSub ? openSub.querySelector('.sub-toggle') : null;
    closeSubs(); if (!desktop.matches) closeNav();
    if (focusTo && nav.contains(document.activeElement)) focusTo.focus(); else if (wasOpen && !desktop.matches) btn.focus();
    btn.querySelector('i').className = 'fa-solid fa-bars';
  });
  var onChange = function () { closeSubs(); closeNav(); btn.querySelector('i').className = 'fa-solid fa-bars'; };
  if (desktop.addEventListener) desktop.addEventListener('change', onChange); else desktop.addListener(onChange);
})();
