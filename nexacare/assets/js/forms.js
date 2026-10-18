// Enquiry forms post to a real server endpoint. Success is only shown when the server confirms it stored the request.
(function () {
  var meta = function (n) { var m = document.querySelector('meta[name="' + n + '"]'); return m ? m.content : ''; };
  var API = meta('nexacare-api') || '/api/enquiry', PHONE = meta('nexacare-phone'), TEL = meta('nexacare-tel');
  var today = new Date().toISOString().slice(0, 10);
  document.querySelectorAll('input[type=date]').forEach(function (d) { d.min = today; });
  document.querySelectorAll('form[data-enquiry]').forEach(init);

  function init(form) {
    var status = form.querySelector('.form-status'), btn = form.querySelector('button[type=submit]');
    form.querySelectorAll('[data-showif]').forEach(function (w) {
      var p = w.dataset.showif.split('='), src = form.elements[p[0]];
      var upd = function () { var on = src.value === p[1]; w.hidden = !on; w.querySelectorAll('input,select,textarea').forEach(function (c) { c.disabled = !on; }); };
      src.addEventListener('change', upd); upd();
    });
    form.addEventListener('submit', function (e) {
      e.preventDefault(); clearErrors(form); var first = null;
      form.querySelectorAll('input,select,textarea').forEach(function (c) {
        if (c.disabled || c.type === 'hidden' || c.type === 'radio' || c.classList.contains('hp-input')) return;
        if (!c.checkValidity()) { mark(c, message(c)); first = first || c; }
      });
      var need = form.dataset.needOne;
      if (need) {
        var names = need.split(',');
        if (!names.some(function (n) { return form.elements[n] && form.elements[n].value.trim(); })) {
          var c0 = form.elements[names[0]]; mark(c0, 'Enter a phone number or an email address so we can reach you.'); first = first || c0;
        }
      }
      if (first) { first.focus(); return; }
      send(form, status, btn);
    });
  }
  function message(c) {
    if (c.validity.valueMissing) return c.type === 'checkbox' ? 'Please tick this box to continue.' : 'This field is required.';
    if (c.validity.typeMismatch) return 'Enter a valid email address.';
    if (c.validity.patternMismatch) return 'Enter a valid phone number, using digits, spaces, + or -.';
    if (c.validity.rangeUnderflow) return 'Choose a date from today onwards.';
    return c.validationMessage;
  }
  function mark(c, msg) {
    c.setAttribute('aria-invalid', 'true');
    var p = document.createElement('p'); p.className = 'field-error'; p.id = c.id + '-err'; p.textContent = msg;
    c.setAttribute('aria-describedby', ((c.getAttribute('aria-describedby') || '') + ' ' + p.id).trim());
    (c.closest('.field') || c.parentElement).appendChild(p);
  }
  function clearErrors(form) {
    form.querySelectorAll('.field-error').forEach(function (p) { p.remove(); });
    form.querySelectorAll('[aria-invalid]').forEach(function (c) { c.removeAttribute('aria-invalid'); });
  }
  function show(status, cls, html) { status.hidden = false; status.className = 'form-status ' + cls; status.innerHTML = html; status.setAttribute('tabindex', '-1'); status.focus(); }
  function send(form, status, btn) {
    var data = {}; new FormData(form).forEach(function (v, k) { if (!form.elements[k] || !form.elements[k].disabled) data[k] = v; });
    data.kind = form.dataset.enquiry; data.consent = !!(form.elements.consent && form.elements.consent.checked);
    var label = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Sending…';
    var ctl = new AbortController(), t = setTimeout(function () { ctl.abort(); }, 15000);
    fetch(API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal: ctl.signal })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (res.ok && res.j.ok) {
          show(status, 'is-success', '<strong>Thank you. Your request has been received.</strong><br>Reference: <strong>' + res.j.reference + '</strong>. ' + (form.dataset.success || '') + ' Please keep this reference if you call us.');
          form.reset(); form.querySelectorAll('[data-showif]').forEach(function (w) { w.hidden = true; });
        } else { fail(status, res.j && res.j.error); }
      })
      .catch(function () { fail(status); })
      .finally(function () { clearTimeout(t); btn.disabled = false; btn.innerHTML = label; });
  }
  function fail(status, msg) {
    show(status, 'is-error', '<strong>We could not send your request.</strong> ' + (msg ? msg + ' ' : 'The online form is unavailable right now. ') +
      'Nothing has been saved. Please call <a href="tel:' + TEL + '">' + PHONE + '</a> or email us instead.');
  }
})();
