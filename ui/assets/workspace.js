(function () {
  'use strict';

  const routes = [
    { href: '/', label: 'Command' },
    { href: '/leads', label: 'Lead Lab' },
    { href: '/velit-batch-scheduler', label: 'Automation' },
    { href: '/email-verifier', label: 'Verify' },
    { href: '/studio', label: 'Agent Studio' },
    { href: '/hunter-search', label: 'Hunter Lab' },
  ];

  const normalizePath = (value) => {
    const clean = String(value || '/').split(/[?#]/)[0].replace(/\/+$/, '');
    return clean || '/';
  };

  // Presentation metadata only: no request builders or execution state live here.
  const pageDesigns = {
    '/': ['command', '01 / THE WORKSPACE', 'Good ideas.', 'Extraordinary reach.', 'Your place to discover prospects, orchestrate agents, and turn research into meaningful connections.', 'Research / Orchestrate / Connect'],
    '/leads': ['leads', '02 / LEAD INTELLIGENCE', 'Find the signal.', 'Make the connection.', 'Discover the companies and people that matter. Bring your next opportunity into focus.', 'Discover / Enrich / Connect'],
    '/velit-batch-scheduler': ['automation', '03 / AUTOMATION', 'Set the rhythm.', 'Expand your reach.', 'Build a thoughtful queue. Let your next round of discovery happen on schedule.', 'Plan / Schedule / Review'],
    '/email-verifier': ['verify', '04 / CONTACT VERIFICATION', 'Better contacts.', 'More confidence.', 'Give every contact a closer look. Verify your workbook and keep the results together.', 'Upload / Verify / Download'],
    '/studio': ['studio', '05 / AGENT STUDIO', 'Shape the thinking.', 'Build what comes next.', 'Give your agents a purpose, the right tools, and a workflow worth running.', 'Configure / Compose / Run'],
    '/hunter-search': ['hunter', '06 / HUNTER LAB', 'A sharper search.', 'A clearer connection.', 'Explore company domains and contact details in your dedicated Hunter workspace.', 'Search / Find / Verify'],
    '/company-chat': ['company', '07 / COMPANY RESEARCH', 'Ask a better question.', 'See the bigger picture.', 'Explore a company, uncover its people, and bring the findings into one report.', 'Ask / Research / Report'],
    '/linkedin-campaign': ['campaign', '08 / OUTREACH STUDIO', 'Start a conversation.', 'Make it meaningful.', 'Bring your contacts, message, and campaign preview together in one considered workspace.', 'Compose / Preview / Review'],
  };
  const pageAliases = { '/dashboard.html': '/', '/leadgen.html': '/leads', '/studio.html': '/studio', '/email_verifier.html': '/email-verifier', '/velit_batch_scheduler.html': '/velit-batch-scheduler', '/hunter_search.html': '/hunter-search', '/company_chat.html': '/company-chat', '/linkedin_campaign.html': '/linkedin-campaign' };
  const currentPath = () => pageAliases[normalizePath(location.pathname)] || normalizePath(location.pathname);
  const navIcons = [
    '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5M8 10.5h5m-2.5-2.5v5"/>',
    '<path d="M13 2 4 14h7l-1 8 10-13h-7z"/>',
    '<path d="m12 3 8 3v6c0 4-8 9-8 9s-8-5-8-9V6zM8 12l3 3 5-6"/>',
    '<rect x="4" y="7" width="16" height="13" rx="4"/><path d="M12 3v4M8 12v2m8-2v2m-7 3h6"/>',
    '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 1v4m0 14v4M1 12h4m14 0h4"/>',
  ];
  const svgIcon = (drawing) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${drawing}</svg>`;

  function installShell() {
    if (document.querySelector('.workspace-nav')) return;
    const current = currentPath();
    const nav = document.createElement('nav');
    nav.className = 'workspace-nav';
    nav.setAttribute('aria-label', 'Primary workspace navigation');
    nav.innerHTML = `
      <a class="workspace-brand" href="/" aria-label="Aryan Agentic Intelligence home">
        <span class="workspace-brand-mark" aria-hidden="true"><img src="/assets/aryan-icon.svg" alt="" width="40" height="40" /></span>
        <span class="workspace-brand-copy">
          <span class="workspace-brand-title">Aryan</span>
          <span class="workspace-brand-subtitle">Agentic intelligence</span>
        </span>
      </a>
      <button class="workspace-menu-button" type="button" aria-expanded="false" aria-label="Open navigation">☰</button>
      <div class="workspace-links">
        ${routes.map((route, index) => `<a class="workspace-link" href="${route.href}"${normalizePath(route.href) === current ? ' aria-current="page"' : ''}>${svgIcon(navIcons[index])}<span>${route.label}</span><small class="workspace-link-index">0${index + 1}</small></a>`).join('')}
      </div>
      <span class="workspace-nav-meta">A place for possibility</span>`;

    const skip = document.createElement('a');
    skip.className = 'workspace-skip-link';
    skip.href = '#workspace-main';
    skip.textContent = 'Skip to workspace';

    document.body.prepend(nav);
    document.body.prepend(skip);

    const main = document.querySelector('main') || document.querySelector('[role="main"]');
    if (main && !main.id) main.id = 'workspace-main';
    if (main) skip.href = `#${main.id}`;

    const button = nav.querySelector('.workspace-menu-button');
    button.innerHTML = '<span></span><span></span>';
    button.addEventListener('click', () => {
      const open = nav.dataset.open !== 'true';
      nav.dataset.open = String(open);
      button.setAttribute('aria-expanded', String(open));
      button.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
      button.innerHTML = '<span></span><span></span>';
    });

    nav.addEventListener('click', (event) => {
      if (event.target.closest('.workspace-link')) {
        nav.dataset.open = 'false';
        button.setAttribute('aria-expanded', 'false');
        button.setAttribute('aria-label', 'Open navigation');
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && nav.dataset.open === 'true') {
        nav.dataset.open = 'false';
        button.setAttribute('aria-expanded', 'false');
        button.setAttribute('aria-label', 'Open navigation');
        button.focus();
      }
    });
  }

  function orbitArtwork() {
    return `<div class="atelier-orbit" aria-hidden="true">
      <div class="orbit-aura"></div><div class="orbit-grid"></div>
      <svg class="orbit-dial" viewBox="0 0 240 240" fill="none">
        <circle cx="120" cy="120" r="112" stroke="currentColor" stroke-dasharray="1 9" />
        <circle cx="120" cy="120" r="101" stroke="currentColor" stroke-dasharray="35 125 12 80" />
        <path d="M120 3v9m0 216v9M3 120h9m216 0h9" stroke="currentColor" />
      </svg>
      <div class="orbit-ring orbit-ring-outer"><i></i></div>
      <div class="orbit-ring orbit-ring-middle"><i></i></div>
      <div class="orbit-ring orbit-ring-inner"><i></i></div>
      <div class="orbit-sweep"></div>
      <div class="orbit-satellite"><span></span></div>
      <div class="orbit-satellite orbit-satellite-secondary"><span></span></div>
      <div class="orbit-core">
        <div class="orbit-core-shell"></div>
        <svg class="orbit-prism" viewBox="0 0 80 80" fill="none">
          <defs><linearGradient id="orbit-prism-gradient" x1="10" y1="10" x2="68" y2="72" gradientUnits="userSpaceOnUse"><stop stop-color="#efffff"/><stop offset=".45" stop-color="#67e8f9"/><stop offset="1" stop-color="#a78bfa"/></linearGradient></defs>
          <path d="m40 6 29 17v34L40 74 11 57V23L40 6Z" fill="#67e8f910" stroke="url(#orbit-prism-gradient)" stroke-width="1.2"/>
          <path d="M40 6v68M11 23l58 34M69 23 11 57M11 23l29 17 29-17M11 57l29-17 29 17" stroke="url(#orbit-prism-gradient)" stroke-width=".7"/>
          <path d="m40 23 15 9v17l-15 9-15-9V32l15-9Z" fill="#a5f3fc24" stroke="#dcfaff" stroke-width=".8"/>
          <circle cx="40" cy="40" r="4" fill="#ecfeff"/>
          <g fill="#d8fcff"><circle cx="40" cy="6" r="2"/><circle cx="69" cy="23" r="2"/><circle cx="69" cy="57" r="2"/><circle cx="40" cy="74" r="2"/><circle cx="11" cy="57" r="2"/><circle cx="11" cy="23" r="2"/></g>
        </svg>
      </div>
      <div class="orbit-particles">${Array.from({ length: 10 }, (_, i) => `<i style="--particle:${i};--angle:${i * 36 + 9}deg;--distance:${78 + (i % 3) * 13}px"></i>`).join('')}</div>
      <span class="orbit-caption">CONNECTED POSSIBILITIES</span>
      <span class="orbit-coordinate">A / 01</span><span class="orbit-signature">INTELLIGENCE, IN MOTION</span>
    </div>`;
  }

  function installPresentation() {
    const design = pageDesigns[currentPath()] || pageDesigns['/'];
    document.body.dataset.workspace = design[0];
    const hero = document.createElement('section');
    hero.className = 'atelier-hero';
    hero.setAttribute('aria-label', design[1].slice(5));
    hero.innerHTML = `<div class="atelier-hero-copy"><p class="atelier-eyebrow"><span></span>${design[1]}</p>
      <h1>${design[2]}<br><em>${design[3]}</em></h1><p class="atelier-description">${design[4]}</p>
      <div class="atelier-disciplines">${design[5].split(' / ').map((label, index) => `<span><b>0${index + 1}</b>${label}</span>`).join('')}</div></div>${orbitArtwork()}`;
    const command = document.querySelector('.command-strip');
    if (command) {
      // Preserve the original quick-action links and their destinations.
      const copy = command.firstElementChild;
      copy.replaceChildren(hero.firstElementChild);
      copy.querySelector('h1').id = 'command-title';
      command.classList.add('atelier-command');
      command.appendChild(hero.lastElementChild);
    } else {
      const anchor = document.getElementById('studio-tabs') || document.querySelector('body > main');
      if (anchor) anchor.before(hero);
    }
    document.querySelectorAll('body > header, body > nav:not(.workspace-nav)').forEach(el => el.classList.add('atelier-toolbar'));
    const verifierTitle = document.querySelector('.shell > header .title-block');
    if (verifierTitle) verifierTitle.classList.add('atelier-replaced-title');
    ['wf-empty', 'ag-empty'].forEach(id => {
      const empty = document.getElementById(id);
      if (!empty) return;
      empty.classList.add('atelier-empty');
      const kind = id === 'wf-empty' ? 'workflow' : 'agent';
      empty.innerHTML = `<span class="atelier-empty-symbol" aria-hidden="true">${svgIcon(navIcons[id === 'wf-empty' ? 2 : 4])}</span><strong>Your next idea starts here.</strong><span>Select a ${kind} to explore it and begin a conversation.</span>`;
    });
    // Associate the existing visible labels without changing input IDs or values.
    document.querySelectorAll('label:not([for])').forEach(label => {
      const control = label.nextElementSibling;
      if (control?.matches('input[id], select[id], textarea[id]')) label.htmlFor = control.id;
    });
  }

  function installInteractionEffects() {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
    let frame = 0;
    let highlighted = null;
    document.addEventListener('pointermove', event => {
      if (motion.matches || !finePointer.matches) return;
      const card = event.target.closest('.card, .glass, .panel, .command-action');
      if (highlighted && highlighted !== card) highlighted.classList.remove('atelier-spotlight');
      highlighted = card;
      if (!card) return;
      cancelAnimationFrame(frame);
      const { clientX, clientY } = event;
      frame = requestAnimationFrame(() => {
        if (highlighted !== card) return;
        const box = card.getBoundingClientRect();
        card.style.setProperty('--spot-x', `${clientX - box.left}px`);
        card.style.setProperty('--spot-y', `${clientY - box.top}px`);
        card.classList.add('atelier-spotlight');
      });
    }, { passive: true });
    document.addEventListener('pointerdown', event => {
      if (motion.matches) return;
      const target = event.target.closest('button, .command-action');
      if (!target || target.disabled) return;
      const rect = target.getBoundingClientRect();
      const ring = document.createElement('span');
      ring.className = 'atelier-click-ring';
      ring.setAttribute('aria-hidden', 'true');
      ring.style.left = `${event.clientX || rect.left + rect.width / 2}px`;
      ring.style.top = `${event.clientY || rect.top + rect.height / 2}px`;
      document.body.appendChild(ring);
      ring.addEventListener('animationend', () => ring.remove(), { once: true });
      setTimeout(() => ring.remove(), 800);
    }, { passive: true });
    // Only visibility classes are observed; existing modal handlers retain control.
    const modals = document.querySelectorAll('[id$="modal"]');
    const observer = new MutationObserver(changes => changes.forEach(({ target }) => {
      if (motion.matches || target.classList.contains('hidden') || getComputedStyle(target).display === 'none') return;
      target.firstElementChild?.animate([{ opacity: 0, transform: 'translateY(12px) scale(.98)' }, { opacity: 1, transform: 'none' }], { duration: 260, easing: 'cubic-bezier(.2,.8,.2,1)' });
    }));
    modals.forEach(modal => observer.observe(modal, { attributes: true, attributeFilter: ['class'] }));
  }

  function improveAccessibility() {
    document.querySelectorAll('input, select, textarea').forEach((control) => {
      if (control.getAttribute('aria-label') || control.getAttribute('aria-labelledby')) return;
      if (control.id) {
        const label = document.querySelector(`label[for="${CSS.escape(control.id)}"]`);
        if (label) return;
      }
      const wrappingLabel = control.closest('label');
      if (wrappingLabel) return;
      const nearby = control.parentElement?.querySelector('label, span');
      const text = nearby?.textContent?.trim();
      if (text) control.setAttribute('aria-label', text.slice(0, 120));
      else if (control.placeholder) control.setAttribute('aria-label', control.placeholder);
    });

    document.querySelectorAll('button:not([aria-label])').forEach((button) => {
      if (!button.textContent.trim() && button.title) button.setAttribute('aria-label', button.title);
    });

    document.querySelectorAll('table').forEach((table) => {
      if (!table.getAttribute('aria-label')) table.setAttribute('aria-label', 'Workspace data table');
    });
  }

  function installReveals() {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const candidates = [...document.querySelectorAll('main > section, main > aside, main .glass, main .card, main .panel')]
      .filter((element, index, all) => !all.some((other) => other !== element && other.contains(element) && other.matches('.glass, .card, .panel')));

    candidates.forEach((element, index) => {
      element.classList.add('ui-reveal');
      element.style.setProperty('--ui-delay', `${Math.min(index, 8) * 42}ms`);
    });

    if (reduceMotion || !('IntersectionObserver' in window)) {
      candidates.forEach((element) => element.classList.add('ui-visible'));
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('ui-visible');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.06, rootMargin: '0px 0px -24px' });
    candidates.forEach((element) => observer.observe(element));
  }

  function installRowMotion() {
    const bodies = document.querySelectorAll('tbody');
    if (!bodies.length || !('MutationObserver' in window)) return;
    const observer = new MutationObserver((changes) => {
      changes.forEach((change) => change.addedNodes.forEach((node) => {
        if (!(node instanceof HTMLElement) || node.tagName !== 'TR' || node.id === 'empty-state') return;
        node.classList.add('ui-new-row');
        window.setTimeout(() => node.classList.remove('ui-new-row'), 500);
      }));
    });
    bodies.forEach((body) => observer.observe(body, { childList: true }));
  }

  const pipelineLabels = ['Input', 'Discovery', 'Validation', 'Enrichment', 'Verification', 'Scoring', 'Deduplication', 'Export ready'];

  function installPipeline() {
    const progress = document.getElementById('progress-wrap');
    if (!progress || document.getElementById('truthful-pipeline')) return;
    const panel = document.createElement('section');
    panel.id = 'truthful-pipeline';
    panel.className = 'pipeline-truth';
    panel.setAttribute('aria-label', 'Lead pipeline state');
    panel.innerHTML = `
      <div class="pipeline-truth-head">
        <span class="pipeline-truth-title">Execution path</span>
        <span class="pipeline-truth-note" id="pipeline-truth-note">Waiting for a request</span>
      </div>
      <div class="pipeline-truth-stages">
        ${pipelineLabels.map((label, index) => `<span class="pipeline-truth-stage" data-stage="${index}" data-state="${index === 0 ? 'ready' : 'pending'}">${label}</span>`).join('')}
      </div>`;
    progress.insertAdjacentElement('afterend', panel);
  }

  function setPipelineState(state, detail) {
    const panel = document.getElementById('truthful-pipeline');
    if (!panel) return;
    const stages = [...panel.querySelectorAll('.pipeline-truth-stage')];
    const note = panel.querySelector('#pipeline-truth-note');
    stages.forEach((stage) => { stage.dataset.state = 'pending'; });

    if (state === 'running') {
      stages[0].dataset.state = 'complete';
      stages[1].dataset.state = 'active';
      note.textContent = detail || 'Backend request running — detailed stages are confirmed on response';
    } else if (state === 'complete') {
      stages.forEach((stage, index) => { stage.dataset.state = index === stages.length - 1 ? 'ready' : 'complete'; });
      note.textContent = detail || 'Pipeline response received — results are ready to review';
    } else if (state === 'failed') {
      const failedIndex = Math.max(0, Math.min(Number(detail?.stageIndex ?? 1), stages.length - 1));
      stages.forEach((stage, index) => { stage.dataset.state = index < failedIndex ? 'complete' : index === failedIndex ? 'failed' : 'pending'; });
      note.textContent = detail?.message || 'The request failed before a complete result was returned';
    } else {
      stages[0].dataset.state = 'ready';
      note.textContent = detail || 'Waiting for a request';
    }
  }

  function setPipelineFromSteps(steps, failure) {
    if (failure) {
      const name = String(failure.stage || '').toLowerCase();
      const stageIndex = name.includes('valid') ? 2 : name.includes('contact') || name.includes('enrich') ? 3 : name.includes('verif') ? 4 : name.includes('quality') || name.includes('scor') ? 5 : 1;
      setPipelineState('failed', { stageIndex, message: failure.reason || `Pipeline stopped at ${failure.stage || 'an unknown stage'}` });
      return;
    }
    if (Array.isArray(steps) && steps.length) setPipelineState('complete');
  }

  window.AryanUI = Object.freeze({
    setPipelineState,
    setPipelineFromSteps,
  });

  function boot() {
    installShell();
    installPresentation();
    improveAccessibility();
    installPipeline();
    installReveals();
    installRowMotion();
    installInteractionEffects();
    document.documentElement.classList.add('ui-ready');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
