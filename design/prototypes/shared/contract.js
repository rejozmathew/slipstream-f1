/* Cross-surface contract helpers shared by TV, desktop and phone.
 *  - event availability (an event may only be shown once it is knowable at the viewer cursor)
 *  - one capability object per session (what this session can honestly show)
 *  - viewer context (session, mode, cursor, delay, speed, follow) carried between presentations
 *  - per-viewer preferences (display size, motion, spoilers) with safe storage
 *  - one motion policy (system setting + toggle) applied to CSS and script animation alike
 *  - the swappable brand mark and the opening overlay
 * Loaded right after engine.js on every page. */
(function () {
  'use strict';
  const SS = window.SS;

  /* ---------------------------------------------------------- availability */
  /** Source time at which an event becomes knowable. Occurrence time `t` is when it happened;
   * `at` (from the server contract) is when the evidence for it exists. Never show before `at`. */
  SS.avail = (e) => (e && e.at != null ? e.at : e ? e.t : Infinity);
  SS.isAvailable = (e, now) => SS.avail(e) <= now;
  SS.eventsUpTo = (s, now) => (s.eventsUpTo ? s.eventsUpTo(now) : s.events.filter((e) => SS.avail(e) <= now));

  /* ---------------------------------------------------------- capabilities */
  /** One object, built once per session and view option, passed to every feature so that the
   * track, following and battle views never disagree about what positions exist. */
  SS.capabilities = function (s, o = {}) {
    const outline = !!(s.circuit && s.circuit.path && s.circuit.path.length > 2);
    let positions = o.map || (outline ? 'outline' : 'line');
    if (positions === 'outline' && !outline) positions = 'line';
    return {
      kind: s.kind,
      outline,
      positions,                         // 'outline' | 'line' | 'none'
      hasPositions: positions !== 'none',
      timingPoints: s.tpStep ? Math.round(1 / s.tpStep) : null,
      live: !!o.live,
      result: s.kind === 'race',
    };
  };

  /* ---------------------------------------------------------- per-viewer preferences */
  const store = (() => { try { const k = '__ss_probe'; localStorage.setItem(k, '1'); localStorage.removeItem(k); return localStorage; } catch (e) { return null; } })();
  const mem = {};
  SS.prefs = {
    get(key, dflt) {
      try { const v = store ? store.getItem('ss.' + key) : mem[key]; return v == null ? dflt : JSON.parse(v); } catch (e) { return dflt; }
    },
    set(key, val) {
      try { const v = JSON.stringify(val); if (store) store.setItem('ss.' + key, v); else mem[key] = v; } catch (e) { /* storage blocked: keep going */ }
    },
  };

  /* ---------------------------------------------------------- motion policy */
  const mq = window.matchMedia ? matchMedia('(prefers-reduced-motion: reduce)') : null;
  const motionListeners = [];
  SS.motion = {
    /** 'system' follows the OS setting; 'reduced' and 'full' are explicit choices. */
    choice: 'system',
    get reduced() { return this.choice === 'reduced' || (this.choice === 'system' && !!(mq && mq.matches)); },
    init(param) {
      this.choice = param === '1' ? 'reduced' : param === '0' ? 'full' : SS.prefs.get('motion', 'system');
      this.apply();
      if (mq) (mq.addEventListener ? mq.addEventListener('change', () => this.apply()) : mq.addListener(() => this.apply()));
      return this;
    },
    set(choice) { this.choice = choice; SS.prefs.set('motion', choice); this.apply(); },
    toggle() { this.set(this.reduced ? 'full' : 'reduced'); },
    apply() {
      document.documentElement.classList.toggle('reduced-motion', this.reduced);
      // Running effects are finished, not left mid-travel.
      if (this.reduced && document.getAnimations) for (const a of document.getAnimations()) { try { if (a.effect && a.effect.getTiming().iterations !== Infinity) a.finish(); } catch (e) { /* ignore */ } }
      for (const fn of motionListeners) fn(this.reduced);
    },
    onChange(fn) { motionListeners.push(fn); },
  };

  /* ---------------------------------------------------------- viewer context */
  /** What a presentation change (desktop → TV → phone) must carry so the viewer lands on the
   * same moment, in the same mode, with the same delay. */
  SS.viewer = {
    fromPlayer(player, extra = {}) {
      return Object.assign({
        s: player.s.label,
        t: Math.round(player.t * 10) / 10,
        live: player.mode === 'live' ? 1 : 0,
        delay: player.delay || 0,
        speed: player.speed,
        play: player.playing ? 1 : 0,
      }, extra);
    },
    query(ctx) {
      const p = new URLSearchParams();
      for (const [k, v] of Object.entries(ctx)) if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
      return p.toString();
    },
    /** Apply a context read from the URL to a freshly created player. */
    apply(player, params) {
      if (params.get('live') === '1') {
        // t is the viewer's cursor; the live edge is t + delay. Keep the cursor where it was.
        const d = Math.max(0, +params.get('delay') || 0);
        player.delay = d; player.requestedDelay = d;
        player.setMode('live');
      } else {
        const d = +params.get('delay') || 0;
        if (d) player.delay = d; // replay sync offset is informational; t already carries the moment
      }
    },
  };

  /* ---------------------------------------------------------- display size (desktop density) */
  SS.DENSITIES = [0.75, 0.8, 0.9, 1];
  SS.density = {
    get(param) {
      const v = param != null ? +param : SS.prefs.get('density', 0.8);
      return SS.DENSITIES.includes(v) ? v : 0.8;
    },
    apply(v) { document.documentElement.style.setProperty('--ui-scale', String(v)); document.documentElement.dataset.density = String(v); },
    set(v) { SS.prefs.set('density', v); this.apply(v); },
  };

  /* ---------------------------------------------------------- brand */
  /** The brand mark is one swappable asset: replace shared/brand/mark-*.png and tile-*.png
   * (and the mask in brand.css) when the final icon lands. */
  SS.brand = {
    base: 'shared/brand/',
    mark(o = {}) {
      const h = o.h || 24;
      return `<span class="brand-mark${o.cls ? ' ' + o.cls : ''}" style="--bm-h:${h}px" role="img" aria-label="Slipstream"><img src="${this.base}mark-${h > 48 ? 192 : 96}.png" alt="" draggable="false"></span>`;
    },
    /** Opening overlay: shown while a session opens. Truthful phase text, no percentages.
     * Removed as soon as the first frame renders; `hold` keeps it up for review. */
    opening(o = {}) {
      const el = document.createElement('div');
      el.className = 'brand-open' + (o.posture ? ' brand-open--' + o.posture : '');
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
      el.innerHTML = `<div class="bo-mark"><img src="${this.base}mark-192.png" alt="" draggable="false"><i class="bo-sweep" aria-hidden="true"></i></div>
        <b class="bo-word">SLIPSTREAM</b>
        <span class="bo-what">${o.title || ''}</span>
        <span class="kerb" aria-hidden="true"></span>
        <span class="bo-phase">${(o.phases || ['Opening session'])[0]}</span>`;
      document.body.appendChild(el);
      const phases = o.phases || [];
      let i = 0;
      const tick = o.hold ? setInterval(() => { i = Math.min(phases.length - 1, i + 1); el.querySelector('.bo-phase').textContent = phases[i]; }, (o.hold || 3000) / Math.max(1, phases.length)) : null;
      return {
        el,
        done() {
          const finish = () => { clearInterval(tick); el.classList.add('is-done'); setTimeout(() => el.remove(), SS.motion.reduced ? 0 : 420); };
          if (o.hold) setTimeout(finish, o.hold); else finish();
        },
      };
    },
  };
})();
