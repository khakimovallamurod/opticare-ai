/**
 * OptiCare UI Motion & Micro-interactions
 * Respects prefers-reduced-motion
 */

(function () {
  'use strict';

  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ── Scroll Reveal via IntersectionObserver ───────────────
  function initScrollReveal() {
    const revealElements = document.querySelectorAll('[data-reveal]');
    if (!revealElements.length) return;

    if (prefersReduced) {
      revealElements.forEach(el => {
        el.style.opacity = '1';
        el.style.transform = 'none';
      });
      return;
    }

    const observer = new IntersectionObserver((entries, obs) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const el = entry.target;
          const delay = parseInt(el.getAttribute('data-delay') || '0', 10);
          setTimeout(() => {
            el.classList.add('reveal-active');
          }, delay);
          obs.unobserve(el);
        }
      });
    }, {
      threshold: 0.1,
      rootMargin: '0px 0px -40px 0px'
    });

    revealElements.forEach(el => observer.observe(el));
  }

  // ── Count-up animation for stat numbers ─────────────────
  function initCountUp() {
    const countElements = document.querySelectorAll('[data-countup]');
    if (!countElements.length) return;

    if (prefersReduced) {
      countElements.forEach(el => {
        const target = parseFloat(el.getAttribute('data-countup'));
        el.textContent = isNaN(target) ? el.textContent : target;
      });
      return;
    }

    const observer = new IntersectionObserver((entries, obs) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const el = entry.target;
          obs.unobserve(el);
          const target = parseFloat(el.getAttribute('data-countup'));
          if (isNaN(target)) return;

          const isFloat = String(target).includes('.');
          const duration = 1200;
          const startTime = performance.now();

          function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // Ease-out cubic
            const ease = 1 - Math.pow(1 - progress, 3);
            const current = ease * target;

            el.textContent = isFloat ? current.toFixed(1) : Math.round(current);

            if (progress < 1) {
              requestAnimationFrame(update);
            } else {
              el.textContent = isFloat ? target.toFixed(1) : target;
            }
          }

          requestAnimationFrame(update);
        }
      });
    }, { threshold: 0.2 });

    countElements.forEach(el => observer.observe(el));
  }

  // ── Toast auto-dismiss ──────────────────────────────────
  function initToasts() {
    const toasts = document.querySelectorAll('[data-toast]');
    toasts.forEach(t => {
      setTimeout(() => {
        t.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        t.style.opacity = '0';
        t.style.transform = 'translateY(-10px)';
        setTimeout(() => t.remove(), 300);
      }, 4000);
    });
  }

  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;

  // ── Custom cursor: dot + trailing ring ──────────────────
  function initCursor() {
    if (!finePointer || prefersReduced) return;

    const root = document.documentElement;
    const dot = document.createElement('div');
    const ring = document.createElement('div');
    const label = document.createElement('span');
    dot.className = 'oc-cursor-dot';
    ring.className = 'oc-cursor-ring';
    dot.setAttribute('aria-hidden', 'true');
    ring.setAttribute('aria-hidden', 'true');
    ring.appendChild(label);
    document.body.append(dot, ring);
    root.classList.add('oc-cursor-enabled');

    let mx = -100, my = -100, rx = -100, ry = -100;

    window.addEventListener('mousemove', (e) => {
      mx = e.clientX;
      my = e.clientY;
      dot.style.transform = `translate3d(${mx}px, ${my}px, 0)`;
      root.classList.add('oc-cursor-on');
    }, { passive: true });

    document.addEventListener('mouseleave', () => root.classList.remove('oc-cursor-on'));
    window.addEventListener('mousedown', () => root.classList.add('oc-cursor-down'));
    window.addEventListener('mouseup', () => root.classList.remove('oc-cursor-down'));

    document.addEventListener('mouseover', (e) => {
      const target = e.target;
      const labelled = target.closest('[data-cursor]');
      const textual = target.closest('input:not([type=file]):not([type=submit]):not([type=button]), textarea, select');
      const interactive = target.closest('a, button, label, [role=button], [data-tilt]');

      root.classList.toggle('oc-cursor-text', !!textual);
      root.classList.toggle('oc-cursor-label', !!labelled);
      root.classList.toggle('oc-cursor-hover', !!interactive && !labelled);
      label.textContent = labelled ? labelled.getAttribute('data-cursor') : '';
    });

    (function loop() {
      rx += (mx - rx) * 0.18;
      ry += (my - ry) * 0.18;
      ring.style.transform = `translate3d(${rx}px, ${ry}px, 0)`;
      requestAnimationFrame(loop);
    })();
  }

  // ── 3D tilt with glare for [data-tilt] ──────────────────
  function initTilt() {
    if (!finePointer || prefersReduced) return;

    document.querySelectorAll('[data-tilt]').forEach((el) => {
      const max = parseFloat(el.getAttribute('data-tilt') || '') || 7;

      el.addEventListener('mousemove', (e) => {
        const r = el.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width;
        const py = (e.clientY - r.top) / r.height;
        el.classList.add('is-tilting');
        el.style.setProperty('--ry', `${(px - 0.5) * max * 2}deg`);
        el.style.setProperty('--rx', `${(0.5 - py) * max * 2}deg`);
        el.style.setProperty('--gx', `${px * 100}%`);
        el.style.setProperty('--gy', `${py * 100}%`);
      });

      el.addEventListener('mouseleave', () => {
        el.classList.remove('is-tilting');
        el.style.setProperty('--rx', '0deg');
        el.style.setProperty('--ry', '0deg');
      });
    });
  }

  // ── Magnetic buttons ────────────────────────────────────
  function initMagnetic() {
    if (!finePointer || prefersReduced) return;

    document.querySelectorAll('[data-magnetic]').forEach((el) => {
      el.addEventListener('mousemove', (e) => {
        const r = el.getBoundingClientRect();
        const dx = e.clientX - (r.left + r.width / 2);
        const dy = e.clientY - (r.top + r.height / 2);
        el.style.transform = `translate(${dx * 0.18}px, ${dy * 0.28}px)`;
      });
      el.addEventListener('mouseleave', () => {
        el.style.transform = '';
      });
    });
  }

  // ── Chart.js Global Animated Draw Defaults ───────────────
  if (window.Chart) {
    window.Chart.defaults.font.family = '"Plus Jakarta Sans", Inter, sans-serif';
    window.Chart.defaults.color = '#5b6b80';
  }
  if (window.Chart && !prefersReduced) {
    window.Chart.defaults.animation = {
      duration: 900,
      easing: 'easeOutQuart',
    };
  }

  // ── Run on DOMContentLoaded ──────────────────────────────
  function initAll() {
    initScrollReveal();
    initCountUp();
    initToasts();
    initCursor();
    initTilt();
    initMagnetic();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
