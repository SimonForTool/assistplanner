// Hlasové zadání: nahrávání přes MediaRecorder (nebo soubor / text) → AI → předvyplnění formuláře.
(function () {
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const recBtn = document.getElementById('rec-btn');
  const fileInput = document.getElementById('audio-file');
  const textBtn = document.getElementById('ai-text-btn');
  const freeText = document.getElementById('free-text');
  const statusEl = document.getElementById('rec-status');
  const resultEl = document.getElementById('ai-result');
  let recorder = null;
  let chunks = [];

  function setStatus(msg) { statusEl.textContent = msg || ''; }

  function showResult(msg, kind) {
    resultEl.className = 'small mt-2 text-' + (kind || 'body-secondary');
    resultEl.textContent = msg || '';
  }

  function fillForm(fields) {
    const form = document.getElementById('task-form');
    for (const [name, value] of Object.entries(fields)) {
      const el = form.elements[name];
      if (!el || value === null || value === undefined) continue;
      el.value = value;
      el.classList.add('ai-filled');
      setTimeout(() => el.classList.remove('ai-filled'), 1800);
    }
    form.elements.title.focus();
  }

  async function send(formData) {
    showResult('');
    setStatus('⏳ Zpracovávám…');
    [recBtn, textBtn].forEach(b => b && (b.disabled = true));
    try {
      const r = await fetch(window.AI_EXTRACT_URL, {
        method: 'POST', body: formData, headers: { 'X-CSRF-Token': csrf },
      });
      const data = await r.json().catch(() => ({ error: 'Neplatná odpověď serveru (' + r.status + ').' }));
      if (!r.ok || data.error) throw new Error(data.error || ('Chyba ' + r.status));
      fillForm(data.fields);
      if (data.transcript) freeText.value = data.transcript;
      showResult(data.ai_used ? '✅ Formulář předvyplněn – zkontrolujte a uložte.'
                              : 'Text vložen do formuláře (bez AI).', 'success');
    } catch (e) {
      showResult('❌ ' + e.message, 'danger');
    } finally {
      setStatus('');
      textBtn.disabled = false;
      if (recBtn && !recBtn.hasAttribute('data-disabled')) recBtn.disabled = false;
    }
  }

  function sendAudio(blob, filename) {
    const fd = new FormData();
    fd.append('audio', blob, filename);
    send(fd);
  }

  textBtn.addEventListener('click', () => {
    const text = freeText.value.trim();
    if (!text) { showResult('Napište nejdřív text.', 'warning'); return; }
    const fd = new FormData();
    fd.append('text', text);
    send(fd);
  });

  if (fileInput) {
    fileInput.addEventListener('change', () => {
      const f = fileInput.files[0];
      if (f) sendAudio(f, f.name);
      fileInput.value = '';
    });
  }

  if (!recBtn) return;
  if (recBtn.disabled) { recBtn.setAttribute('data-disabled', '1'); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    recBtn.disabled = true;
    recBtn.setAttribute('data-disabled', '1');
    setStatus('Prohlížeč nepodporuje nahrávání – použijte soubor nebo text.');
    return;
  }

  function pickMime() {
    const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'];
    return types.find(t => MediaRecorder.isTypeSupported(t)) || '';
  }

  recBtn.addEventListener('click', async () => {
    if (recorder && recorder.state === 'recording') { recorder.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = pickMime();
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunks = [];
      recorder.ondataavailable = e => e.data.size && chunks.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach(t => t.stop());
        recBtn.classList.remove('recording');
        recBtn.textContent = '⏺️ Nahrávat';
        const type = recorder.mimeType || 'audio/webm';
        const ext = type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm';
        sendAudio(new Blob(chunks, { type }), 'nahravka.' + ext);
      };
      recorder.start();
      recBtn.classList.add('recording');
      recBtn.textContent = '⏹️ Zastavit a zpracovat';
      setStatus('🔴 Nahrávám… mluvte.');
    } catch (e) {
      setStatus('Mikrofon není dostupný: ' + e.message);
    }
  });
})();
