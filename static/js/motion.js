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

  // ── Chart.js Global Animated Draw Defaults ───────────────
  if (window.Chart && !prefersReduced) {
    window.Chart.defaults.animation = {
      duration: 900,
      easing: 'easeOutQuart',
    };
  }

  // ── Run on DOMContentLoaded ──────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initScrollReveal();
      initCountUp();
      initToasts();
    });
  } else {
    initScrollReveal();
    initCountUp();
    initToasts();
  }
})();
