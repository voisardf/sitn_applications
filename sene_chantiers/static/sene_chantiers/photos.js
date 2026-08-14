/* Photo block: upload, per-photo caption, and polling while the worker
   sanitises. Uploads are staged immediately so the inspector can carry on
   filling the report; a spinner marks each photo until /data has it. */
(function () {
  const block = document.getElementById('photo-block');
  if (!block) return;

  const kind = block.dataset.kind;
  const reportId = block.dataset.report;
  const strip = document.getElementById('photo-strip');
  const input = document.getElementById('photo-input');
  const dropzone = document.getElementById('photo-dropzone');
  const modalEl = document.getElementById('caption-modal');
  const captionText = document.getElementById('caption-text');
  let currentPhoto = null;
  let pollTimer = null;

  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const urls = {
    upload: `/sene_chantiers/rapport/${kind}/${reportId}/photos/`,
    status: `/sene_chantiers/rapport/${kind}/${reportId}/photos/etat/`,
    caption: id => `/sene_chantiers/photos/${id}/remarques/`,
    remove: id => `/sene_chantiers/photos/${id}/supprimer/`,
  };

  function post(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf },
      body: body,
    }).then(r => r.json().then(data => ({ ok: r.ok, data })));
  }

  function figureFor(photo) {
    let fig = strip.querySelector(`[data-photo="${photo.id}"]`);
    if (!fig) {
      fig = document.createElement('figure');
      fig.className = 'sc-photo';
      fig.dataset.photo = photo.id;
      fig.innerHTML = `
        <div class="sc-photo-frame"></div>
        <figcaption class="sc-photo-caption"></figcaption>
        <div class="sc-photo-actions">
          <button type="button" class="btn btn-sm btn-outline-secondary js-caption">Remarques</button>
          <button type="button" class="btn sc-icon-btn is-pdf js-delete" title="Supprimer">
            <i class="bi bi-trash"></i>
          </button>
        </div>`;
      strip.appendChild(fig);
      const empty = document.getElementById('photo-empty');
      if (empty) empty.remove();
    }
    return fig;
  }

  function paint(photo) {
    const fig = figureFor(photo);
    fig.dataset.status = photo.status;
    const frame = fig.querySelector('.sc-photo-frame');
    if (photo.status === 'done' && photo.url) {
      frame.innerHTML = `<img src="${photo.url}" alt="Photo du contrôle">`;
    } else if (photo.status === 'failed') {
      frame.innerHTML = `<div class="sc-photo-failed" title="${photo.error}">
        <i class="bi bi-exclamation-triangle"></i></div>`;
    } else {
      frame.innerHTML = `<div class="sc-photo-pending">
        <div class="spinner-border spinner-border-sm" role="status"></div>
        <span>Traitement…</span></div>`;
    }
    fig.querySelector('.sc-photo-caption').textContent = photo.caption || '';
  }

  function pollIfBusy() {
    const busy = strip.querySelector('[data-status="pending"], [data-status="processing"]');
    clearTimeout(pollTimer);
    if (!busy) return;
    pollTimer = setTimeout(function () {
      fetch(urls.status)
        .then(r => r.json())
        .then(data => { data.photos.forEach(paint); pollIfBusy(); })
        .catch(() => {});
    }, 3000);
  }

  function upload(files) {
    [...files].forEach(file => {
      const body = new FormData();
      body.append('photo', file);
      post(urls.upload, body).then(({ ok, data }) => {
        if (!ok) { window.alert(data.error || 'Téléversement refusé.'); return; }
        paint(data);
        pollIfBusy();
      });
    });
  }

  if (input) input.addEventListener('change', () => { upload(input.files); input.value = ''; });

  if (dropzone) {
    ['dragenter', 'dragover'].forEach(evt =>
      dropzone.addEventListener(evt, e => {
        e.preventDefault(); dropzone.classList.add('is-over');
      }));
    ['dragleave', 'drop'].forEach(evt =>
      dropzone.addEventListener(evt, e => {
        e.preventDefault(); dropzone.classList.remove('is-over');
      }));
    dropzone.addEventListener('drop', e => upload(e.dataTransfer.files));
  }

  strip.addEventListener('click', function (event) {
    const fig = event.target.closest('.sc-photo');
    if (!fig) return;
    if (event.target.closest('.js-caption')) {
      currentPhoto = fig.dataset.photo;
      captionText.value = fig.querySelector('.sc-photo-caption').textContent.trim();
      bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
    if (event.target.closest('.js-delete')) {
      if (!window.confirm('Supprimer cette photo ?')) return;
      post(urls.remove(fig.dataset.photo), new FormData()).then(() => fig.remove());
    }
  });

  const saveBtn = document.getElementById('caption-save');
  if (saveBtn) {
    saveBtn.addEventListener('click', function () {
      const body = new FormData();
      body.append('caption', captionText.value);
      post(urls.caption(currentPhoto), body).then(({ data }) => {
        paint(data);
        bootstrap.Modal.getOrCreateInstance(modalEl).hide();
      });
    });
  }

  pollIfBusy();
})();
