// Enquiry forms post to a real server endpoint. Success is shown only when the server confirms it stored the request,
// including the branch the visitor chose. Validation runs on blur and on submit with clear messages.
(function () {
  var meta = function (n) { var m = document.querySelector('meta[name="' + n + '"]'); return m ? m.content : ''; };
  var API = meta('nexacare-api') || '/api/enquiry', PHONE = meta('nexacare-phone'), TEL = meta('nexacare-tel');
  var today = new Date().toISOString().slice(0, 10);
  document.querySelectorAll('input[type=date]').forEach(function (d) { d.min = today; });
  document.querySelectorAll('form[data-enquiry]').forEach(init);

  function skip(c) { return c.disabled || c.type === 'hidden' || c.type === 'radio' || c.classList.contains('hp-input') || c.closest('.hp'); }
  function init(form) {
    var status = form.querySelector('.form-status'), btn = form.querySelector('button[type=submit]');
    form.querySelectorAll('[data-showif]').forEach(function (w) {
      var p = w.dataset.showif.split('='), src = form.elements[p[0]];
      var upd = function () { var on = src.value === p[1]; w.hidden = !on; w.querySelectorAll('input,select,textarea').forEach(function (c) { c.disabled = !on; }); };
      src.addEventListener('change', upd); upd();
    });
    form.querySelectorAll('input,select,textarea').forEach(function (c) {
      if (skip(c)) return;
      c.addEventListener('blur', function () { if (c.type === 'checkbox' || c.value !== '' || c.hasAttribute('aria-invalid')) check(c); });
      c.addEventListener(c.tagName === 'SELECT' || c.type === 'checkbox' ? 'change' : 'input', function () { if (c.hasAttribute('aria-invalid')) check(c); });
    });
    form.addEventListener('submit', function (e) {
      e.preventDefault(); status.hidden = true; var bad = [];
      form.querySelectorAll('input,select,textarea').forEach(function (c) { if (!skip(c) && !check(c)) bad.push(c); });
      var need = form.dataset.needOne;
      if (need) {
        var names = need.split(',');
        if (!names.some(function (n) { return form.elements[n] && form.elements[n].value.trim(); })) {
          var c0 = form.elements[names[0]]; mark(c0, 'Enter a phone number or an email address so we can reach you.'); bad.push(c0);
        }
      }
      if (bad.length) {
        show(status, 'is-error', '<strong>Please check ' + (bad.length === 1 ? 'one field' : bad.length + ' fields') + ' before sending.</strong> The fields to correct are marked below.');
        bad[0].focus(); return;
      }
      send(form, status, btn);
    });
  }
  function label(c) { var l = c.id && document.querySelector('label[for="' + c.id + '"]'); return l ? l.childNodes[0].textContent.trim().toLowerCase() : 'this field'; }
  function message(c) {
    if (c.validity.valueMissing) {
      if (c.type === 'checkbox') return 'Please tick this box to continue.';
      if (c.name === 'branch') return 'Please choose a branch, or choose \u201cNo preference\u201d.';
      if (c.tagName === 'SELECT') return 'Please choose an option for ' + label(c) + '.';
      return 'Please fill in ' + label(c) + '.';
    }
    if (c.validity.typeMismatch) return 'Enter a valid email address, for example name@example.com.';
    if (c.validity.patternMismatch) return 'Enter a valid phone number, using digits, spaces, + or -.';
    if (c.validity.rangeUnderflow) return 'Choose a date from today onwards.';
    return c.validationMessage;
  }
  function check(c) {
    unmark(c);
    if (c.checkValidity()) return true;
    mark(c, message(c)); return false;
  }
  function mark(c, msg) {
    unmark(c); c.setAttribute('aria-invalid', 'true');
    var p = document.createElement('p'); p.className = 'field-error'; p.id = c.id + '-err'; p.textContent = msg;
    c.setAttribute('aria-describedby', ((c.getAttribute('aria-describedby') || '') + ' ' + p.id).trim());
    (c.closest('.field') || c.parentElement).appendChild(p);
  }
  function unmark(c) {
    var old = document.getElementById(c.id + '-err'); if (old) old.remove();
    c.removeAttribute('aria-invalid');
    var d = (c.getAttribute('aria-describedby') || '').split(' ').filter(function (x) { return x && x !== c.id + '-err'; }).join(' ');
    if (d) c.setAttribute('aria-describedby', d); else c.removeAttribute('aria-describedby');
  }
  function show(status, cls, html) { status.hidden = false; status.className = 'form-status ' + cls; status.innerHTML = html; status.setAttribute('tabindex', '-1'); status.focus(); }
  function send(form, status, btn) {
    var data = {}; new FormData(form).forEach(function (v, k) { if (!form.elements[k] || !form.elements[k].disabled) data[k] = v; });
    data.kind = form.dataset.enquiry; data.consent = !!(form.elements.consent && form.elements.consent.checked);
    var bsel = form.elements.branch, bname = bsel && bsel.value && bsel.value !== 'no-preference' ? bsel.options[bsel.selectedIndex].text : '';
    var lab = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Sending\u2026';
    var ctl = new AbortController(), t = setTimeout(function () { ctl.abort(); }, 15000);
    fetch(API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal: ctl.signal })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (res.ok && res.j.ok) {
          var ref = document.createElement('strong'); ref.textContent = res.j.reference;
          var where = bname ? ' for <strong></strong>' : '';
          show(status, 'is-success', '<strong>Thank you. Your request has been received' + where + '.</strong><br>Reference: <span data-ref></span>. ' + (form.dataset.success || '') + ' Please keep this reference if you call us.');
          status.querySelector('[data-ref]').appendChild(ref);
          if (bname) status.querySelector('strong strong').textContent = bname;
          form.reset(); form.querySelectorAll('[data-showif]').forEach(function (w) { w.hidden = true; });
          form.querySelectorAll('select[name=branch]').forEach(function (s) { s.dispatchEvent(new Event('change', { bubbles: true })); });
        } else { fail(status, res.j && res.j.error); }
      })
      .catch(function () { fail(status); })
      .finally(function () { clearTimeout(t); btn.disabled = false; btn.innerHTML = lab; });
  }
  function fail(status, msg) {
    var m = document.createElement('span'); if (msg) m.textContent = msg + ' ';
    show(status, 'is-error', '<strong>We could not send your request.</strong> <span data-m></span>' + (msg ? '' : 'The online form is unavailable right now. ') +
      'Nothing has been saved. Please call <a href="tel:' + TEL + '">' + PHONE + '</a> or email us instead.');
    status.querySelector('[data-m]').appendChild(m);
  }
})();
