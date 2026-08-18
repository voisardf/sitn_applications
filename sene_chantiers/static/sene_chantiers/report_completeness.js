/* Completeness guard for the report forms.
 *
 * Two halves, deliberately. The server decides authoritatively and its
 * verdict is rendered as a banner naming the sections still to fill; this
 * script only catches the same case earlier, before a round-trip, because
 * an inspector pressing "Enregistrer" from a tab they have just completed
 * has no way of knowing something is missing in a tab they cannot see.
 *
 * Saving a draft is never blocked: a draft is allowed to be incomplete.
 */
(function () {
  'use strict';

  const form = document.querySelector('form[data-completeness-guard]');
  if (!form) return;

  const SECTIONS = { tab01: '01', tab02: '02', tab03: '03', tab04: '04' };

  function label(pane) {
    const code = SECTIONS[pane.id];
    const tab = document.querySelector(`[data-tab-code="${pane.id}"]`);
    const text = tab ? tab.textContent.trim().replace(/\s+/g, ' ') : code;
    return text || code;
  }

  // A field counts as missing when it is required and still empty. Radio
  // groups need the whole group inspected, not the individual input.
  function incompletePanes() {
    const found = [];
    form.querySelectorAll('.tab-pane').forEach(pane => {
      const required = pane.querySelectorAll('[required]');
      let missing = false;
      required.forEach(el => {
        if (el.type === 'radio') {
          if (!pane.querySelector(`[name="${el.name}"]:checked`)) missing = true;
        } else if (!el.value.trim()) {
          missing = true;
        }
      });
      if (missing) found.push(pane);
    });
    return found;
  }

  function mark(panes) {
    document.querySelectorAll('[data-tab-code]').forEach(tab => {
      tab.classList.remove('is-incomplete');
    });
    panes.forEach(pane => {
      const tab = document.querySelector(`[data-tab-code="${pane.id}"]`);
      if (tab) tab.classList.add('is-incomplete');
    });
  }

  form.addEventListener('submit', function (event) {
    // "Enregistrer le brouillon" submits with its own name; leave it alone.
    const submitter = event.submitter;
    if (submitter && submitter.name === 'save_draft') return;

    const panes = incompletePanes();
    if (!panes.length) return;

    mark(panes);
    const names = panes.map(label).join(', ');
    const message =
      `Des informations obligatoires manquent dans : ${names}.\n\n` +
      `OK pour compléter maintenant, Annuler pour enregistrer un brouillon.`;
    if (window.confirm(message)) {
      event.preventDefault();
      const tab = document.querySelector(`[data-tab-code="${panes[0].id}"]`);
      if (tab) tab.click();
      panes[0].querySelector('[required]')?.focus();
    } else {
      event.preventDefault();
      const draft = form.querySelector('[name="save_draft"]');
      if (draft) draft.click();
    }
  });

  // Deep-link from the server-side banner to the offending tab.
  document.querySelectorAll('[data-goto-tab]').forEach(link => {
    link.addEventListener('click', function (event) {
      event.preventDefault();
      const tab = document.querySelector(
        `[data-tab-code="${link.dataset.gotoTab}"]`);
      if (tab) tab.click();
    });
  });

  // On arrival after a rejected save, flag the tabs straight away.
  if (document.getElementById('incomplete-warning')) mark(incompletePanes());
})();
