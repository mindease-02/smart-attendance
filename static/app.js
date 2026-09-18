/* Shared UI: reveals, counters, nav, toasts, table search */
(function () {
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Mobile nav
  var t = document.getElementById('navToggle'), l = document.getElementById('navLinks');
  if (t && l) t.addEventListener('click', function () {
    var open = l.classList.toggle('open');
    t.setAttribute('aria-expanded', open);
  });

  // Active nav link
  var page = document.body.dataset.page || '';
  document.querySelectorAll('[data-nav]').forEach(function (a) {
    if (a.dataset.nav === page) a.classList.add('active');
  });

  // Scroll reveals
  var els = document.querySelectorAll('.reveal');
  if (reduce || !('IntersectionObserver' in window)) {
    els.forEach(function (e) { e.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
      });
    }, { threshold: 0.12 });
    els.forEach(function (e) { io.observe(e); });
  }

  // Animated counters
  document.querySelectorAll('[data-count]').forEach(function (el) {
    var target = parseInt(el.dataset.count, 10) || 0;
    if (reduce) { el.textContent = target; return; }
    var start = null, dur = 1100;
    function frame(ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(target * eased);
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  });

  // Auto-dismiss toasts
  document.querySelectorAll('[data-toast]').forEach(function (el) {
    setTimeout(function () {
      el.classList.add('out');
      setTimeout(function () { el.remove(); }, 450);
    }, 4200);
  });

  // Generic table filter: input[data-filter-for="tableId"]
  document.querySelectorAll('[data-filter-for]').forEach(function (input) {
    var table = document.getElementById(input.dataset.filterFor);
    if (!table) return;
    var emptyRow = table.querySelector('[data-empty]');
    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase(), visible = 0;
      table.querySelectorAll('tbody tr[data-row]').forEach(function (tr) {
        var hit = tr.textContent.toLowerCase().indexOf(q) !== -1;
        // status chip filter
        var chip = document.querySelector('.chip.on[data-status]');
        if (hit && chip && chip.dataset.status) {
          hit = tr.dataset.status === chip.dataset.status;
        }
        tr.style.display = hit ? '' : 'none';
        if (hit) visible++;
      });
      var count = document.querySelector('[data-count-for="' + table.id + '"]');
      if (count) count.textContent = visible + ' shown';
      if (emptyRow) emptyRow.style.display = visible ? 'none' : '';
    });
  });

  // Status chips
  document.querySelectorAll('.chip[data-status]').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var was = chip.classList.contains('on');
      document.querySelectorAll('.chip[data-status]').forEach(function (c) { c.classList.remove('on'); });
      if (!was) chip.classList.add('on');
      var input = document.querySelector('[data-filter-for="' + chip.dataset.table + '"]');
      if (input) input.dispatchEvent(new Event('input'));
    });
  });
})();
