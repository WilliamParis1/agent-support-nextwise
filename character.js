// All dialogue stays in the character's bubble. Only stable poses are persisted.
(() => {
  const scene = document.querySelector('#professor-scene');
  const speech = document.querySelector('#professor-speech');
  const pointing = document.querySelector('#professor');
  const pose = document.querySelector('#professor-pose');
  const toggle = document.querySelector('#character-toggle');
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const storageKey = 'synapse-sleeping';
  let state = 'awake';
  let transitionTimer;
  let speechTimer;
  let target;
  let assetsReady = false;

  function say(text, animate = false) {
    clearTimeout(speechTimer);
    scene.classList.remove('is-speaking');
    // Announce the complete sentence once; visual typing is decorative.
    speech.textContent = text;
    if (animate && !motion.matches && !document.hidden) {
      scene.classList.add('is-speaking');
      speechTimer = setTimeout(() => scene.classList.remove('is-speaking'), 1500);
    }
  }

  function setState(next) {
    state = next;
    scene.dataset.state = next;
    const busy = next === 'walking' || next === 'waking';
    scene.setAttribute('aria-busy', String(busy));
    toggle.disabled = busy || !assetsReady;
    pointing.hidden = next !== 'awake';
    pose.hidden = next === 'awake';
    pose.setAttribute('aria-label', {
      walking: 'Mr Synapse marche de dos vers son lit.',
      asleep: 'Mr Synapse dort dans son lit, sous sa couverture bleue.',
      waking: 'Mr Synapse se réveille et revient de face avec sa canne.'
    }[next] || 'Mr Synapse');
    toggle.textContent = {
      awake: 'Bonne nuit', walking: 'Bonne nuit…', asleep: 'Bonjour', waking: 'Bonjour…'
    }[next];
  }

  function settle(next, greet = true) {
    clearTimeout(transitionTimer);
    target = undefined;
    setState(next);
    try { localStorage.setItem(storageKey, String(next === 'asleep')); } catch { /* Storage may be disabled. */ }
    say(next === 'asleep' ? 'Zzz…' : greet ? 'Bonjour ! Le point du jour est juste à côté.' : 'Bonjour ! Moi, c’est Mr Synapse.', next === 'awake');
  }

  toggle.addEventListener('click', () => {
    if (!assetsReady || (state !== 'awake' && state !== 'asleep')) return;
    clearTimeout(speechTimer);
    scene.classList.remove('is-speaking');
    target = state === 'awake' ? 'asleep' : 'awake';
    if (motion.matches) { settle(target); return; }
    setState(target === 'asleep' ? 'walking' : 'waking');
    say(target === 'asleep' ? 'Bonne nuit… À demain !' : 'Bonjour ! J’arrive…');
    transitionTimer = setTimeout(() => settle(target), target === 'asleep' ? 1500 : 1300);
  });

  motion.addEventListener('change', () => {
    if (motion.matches) {
      clearTimeout(speechTimer);
      scene.classList.remove('is-speaking');
      if (target) settle(target);
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearTimeout(speechTimer);
      scene.classList.remove('is-speaking');
      if (target) settle(target);
    }
  });

  const sprites = new Image();
  sprites.src = 'assets/synapse-poses.png';
  sprites.decode().then(() => {
    assetsReady = true;
    let asleep = false;
    try { asleep = localStorage.getItem(storageKey) === 'true'; } catch { /* Default to awake. */ }
    settle(asleep ? 'asleep' : 'awake', false);
  }).catch(() => {
    // Keep the original portrait if an asset fails; no invisible or stuck character.
    setState('awake');
    say('Je suis là ! Le point du jour est juste à côté.');
  });
})();
