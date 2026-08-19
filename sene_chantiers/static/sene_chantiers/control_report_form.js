/* Aides de saisie des formulaires de rapport.
 *
 * Quatre comportements, tous purement confortables : le serveur reste seul
 * juge de ce qui est enregistré, et le formulaire fonctionne sans ce
 * script, en cliquant chaque champ à la main.
 *
 * Chargé par les deux rapports. La mémoire de l'onglet vaut pour les deux ;
 * les trois autres aides ne trouvent simplement rien à faire sur le
 * rapport de suivi, qui n'a ni checklist ni mesures à ajouter.
 */
(function () {
  'use strict';

  const form = document.getElementById('control-report-form')
            || document.getElementById('followup-form');
  if (!form) return;

  /* ------------------------------------------------------------------
   * 1. Retenir l'onglet actif, pour y revenir après un enregistrement.
   * ---------------------------------------------------------------- */
  const activeTab = document.getElementById('active-tab');
  if (activeTab) {
    document.querySelectorAll('[data-bs-toggle="tab"]').forEach(button => {
      button.addEventListener('shown.bs.tab', function () {
        const target = button.getAttribute('data-bs-target') || '';
        activeTab.value = target.replace('#', '') || activeTab.value;
      });
    });
  }

  /* ------------------------------------------------------------------
   * 2. Section 04 : appliquer une conformité à tout un thème.
   *    Les lignes restent modifiables individuellement ensuite.
   * ---------------------------------------------------------------- */
  document.querySelectorAll('.sc-bulk-input').forEach(input => {
    input.addEventListener('change', function () {
      const row = input.closest('.sc-bulk-row');
      const body = row ? row.closest('tbody') : null;
      if (!body) return;
      body.querySelectorAll('tr:not(.sc-bulk-row)').forEach(line => {
        const choice = line.querySelector(
          `input[type="radio"][value="${input.value}"]`);
        if (choice && !choice.disabled) {
          choice.checked = true;
          // Prévenir la cascade d'appréciation, qui écoute "change".
          choice.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
    });
  });

  /* ------------------------------------------------------------------
   * 3. Section 03 : la corbeille marque la ligne, elle ne la supprime
   *    pas tout de suite. La suppression n'a lieu qu'à l'enregistrement,
   *    donc le geste reste réversible tant que rien n'est envoyé.
   * ---------------------------------------------------------------- */
  form.addEventListener('change', function (event) {
    const box = event.target;
    if (!box.matches('.sc-measure-delete input[type="checkbox"]')) return;
    const row = box.closest('.measure-row');
    if (row) row.classList.toggle('is-deleted', box.checked);
  });

  /* ------------------------------------------------------------------
   * 4. Section 02 : reprendre les observations de la section 04 comme
   *    remarques principales, tant que l'inspecteur n'a rien écrit
   *    lui-même dans la section 02. Dès qu'il y touche, on n'y revient
   *    plus — sa rédaction prime sur la reprise automatique.
   * ---------------------------------------------------------------- */
  const remarks = document.querySelectorAll('[name$="-synthesis_remarks"]');
  remarks.forEach(field => {
    if (field.value.trim()) field.dataset.edited = 'true';
    field.addEventListener('input', function () {
      field.dataset.edited = 'true';
    });
  });

  function mirrorObservations() {
    document.querySelectorAll('[name$="-detail_observations"]').forEach(source => {
      // themes-2-detail_observations -> themes-2-synthesis_remarks
      const target = document.querySelector(
        `[name="${source.name.replace('-detail_observations', '-synthesis_remarks')}"]`);
      if (target && target.dataset.edited !== 'true') {
        target.value = source.value;
      }
    });
  }

  document.addEventListener('input', function (event) {
    if (event.target.matches('[name$="-detail_observations"]')) {
      mirrorObservations();
    }
  });
  mirrorObservations();
})();
