// Hlasové zadání → vyplnění formuláře úkolu.
// S OpenAI (data-whisper="1"): nahrávka přes MediaRecorder → Whisper + GPT na serveru.
// Bez OpenAI: přepis řeči přímo v prohlížeči (Web Speech API, čeština) → pravidlový rozbor na serveru.
//
// Režimy:  fill    – první vyplnění, přepíše pole formuláře
//          append  – doplní text do poznámky, ostatní pole jen pokud jsou prázdná
//          replace – nahradí poznámku, ostatní pole jen pokud jsou prázdná
// Po prvním vyplnění (nebo v detailu úkolu) se nabízí jen append / replace,
// aby nové diktování nepřepsalo název a další údaje.
(function () {
  const panel = document.getElementById('voice');
  const form = document.getElementById('task-form');
  if (!panel || !form) return;

  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const recBtn = document.getElementById('rec-btn');
  const fileInput = document.getElementById('audio-file');
  const freeText = document.getElementById('free-text');
  const statusEl = document.getElementById('rec-status');
  const resultEl = document.getElementById('ai-result');
  const modeButtons = panel.querySelectorAll('[data-voice-mode]');
  const useWhisper = recBtn.dataset.whisper === '1';
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let filled = panel.dataset.filled === '1';
  let busy = false;

  function setStatus(msg) { statusEl.textContent = msg || ''; }

  function showResult(msg, kind) {
    resultEl.className = 'small mt-2 text-' + (kind || 'body-secondary');
    resultEl.textContent = msg || '';
  }

  function setRecording(on) {
    recBtn.classList.toggle('recording', on);
    recBtn.querySelector('.ico-mic').style.display = on ? 'none' : 'inline-flex';
    recBtn.querySelector('.ico-stop').style.display = on ? 'inline-flex' : 'none';
    recBtn.setAttribute('aria-label', on ? 'Zastavit' : 'Nahrávat');
  }

  function setFilled(on) {
    filled = on;
    document.getElementById('voice-fill-actions').classList.toggle('d-none', on);
    document.getElementById('voice-note-actions').classList.toggle('d-none', !on);
    if (on) {
      document.getElementById('voice-title').textContent = 'Nadiktujte doplnění';
      document.getElementById('rec-label').textContent =
        'Klepněte na mikrofon, nadiktujte doplnění a pak zvolte, co se má s poznámkou stát.';
      freeText.placeholder = 'Např.: do poznámky přinést projektor a podklady k rozpočtu';
    }
  }

  function setBusy(on) {
    busy = on;
    modeButtons.forEach(b => { b.disabled = on; });
    if (!recBtn.hasAttribute('data-disabled')) recBtn.disabled = on;
  }

  function highlight(el) {
    el.classList.add('ai-filled');
    setTimeout(() => el.classList.remove('ai-filled'), 1800);
  }

  function setField(name, value) {
    const el = form.elements[name];
    if (!el || value === null || value === undefined || value === '') return false;
    el.value = value;
    highlight(el);
    return true;
  }

  function isEmpty(name) {
    const el = form.elements[name];
    return !el || !String(el.value).trim();
  }

  // --- Použití výsledku podle režimu ---
  function apply(mode, fields) {
    if (mode === 'fill') {
      for (const [name, value] of Object.entries(fields)) setField(name, value);
      setFilled(true);
      freeText.value = '';
      showResult('✅ Formulář vyplněn – zkontrolujte a uložte. Další diktování už jen doplní poznámku.', 'success');
      if (window.innerWidth < 992) form.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }

    // append / replace: poznámka + jen prázdná pole
    const note = (fields.note || fields.description || '').trim();
    const desc = form.elements.description;
    if (mode === 'append') {
      const current = desc.value.trim();
      desc.value = current ? current + '\n' + note : note;
    } else {
      desc.value = note;
    }
    highlight(desc);

    const added = [];
    for (const name of ['assignee_target', 'location', 'due_date']) {
      if (isEmpty(name) && setField(name, fields[name])) added.push(name);
    }
    if (added.includes('assignee_target')) setField('task_type', 'COMMITMENT');
    // Prioritu jen zvýšíme ze „Střední“, když ji diktát výslovně uvádí
    const prio = form.elements.priority;
    if (prio && prio.value === 'MEDIUM' && fields.priority && fields.priority !== 'MEDIUM') {
      setField('priority', fields.priority);
      added.push('priority');
    }

    const labels = { assignee_target: 'komu slíbeno', location: 'místo', due_date: 'termín', priority: 'priorita' };
    const extra = added.length ? ' Doplněno také: ' + added.map(n => labels[n]).join(', ') + '.' : '';
    showResult((mode === 'append' ? '✅ Poznámka doplněna.' : '✅ Poznámka nahrazena.') + extra +
               ' Nezapomeňte uložit.', 'success');
    freeText.value = '';
  }

  async function request(formData) {
    const r = await fetch(window.AI_EXTRACT_URL, {
      method: 'POST', body: formData, headers: { 'X-CSRF-Token': csrf },
    });
    const data = await r.json().catch(() => ({ error: 'Neplatná odpověď serveru (' + r.status + ').' }));
    if (!r.ok || data.error) throw new Error(data.error || ('Chyba ' + r.status));
    return data;
  }

  // mode = null → jen přepis do textového pole (uživatel pak zvolí doplnit / nahradit)
  async function process(formData, mode) {
    if (busy) return;
    setBusy(true);
    showResult('');
    setStatus(mode ? '⏳ Zpracovávám…' : '⏳ Přepisuji…');
    try {
      const data = await request(formData);
      if (mode) {
        apply(mode, data.fields);
      } else {
        freeText.value = data.transcript || '';
        showResult('Text je připraven – zvolte „Doplnit poznámku“, nebo „Nahradit poznámku“.', 'primary');
      }
    } catch (e) {
      showResult('❌ ' + e.message, 'danger');
    } finally {
      setBusy(false);
      setStatus('');
    }
  }

  function processText(mode) {
    const text = freeText.value.trim();
    if (!text) { showResult('Nejdřív nadiktujte nebo napište text.', 'warning'); return; }
    const fd = new FormData();
    fd.append('text', text);
    process(fd, mode);
  }

  function processAudio(blob, filename) {
    const fd = new FormData();
    fd.append('audio', blob, filename);
    process(fd, filled ? null : 'fill');
  }

  modeButtons.forEach(btn => btn.addEventListener('click', () => processText(btn.dataset.voiceMode)));

  if (fileInput) {
    fileInput.addEventListener('change', () => {
      const f = fileInput.files[0];
      if (f) processAudio(f, f.name);
      fileInput.value = '';
    });
  }

  // Po skončení diktátu: poprvé rovnou vyplnit, jinak nechat volbu na uživateli
  function afterTranscript() {
    const text = freeText.value.trim();
    if (!text) return;
    if (filled) {
      showResult('Text je připraven – zvolte „Doplnit poznámku“, nebo „Nahradit poznámku“.', 'primary');
    } else {
      processText('fill');
    }
  }

  function disableMic(msg) {
    recBtn.disabled = true;
    recBtn.setAttribute('data-disabled', '1');
    document.getElementById('rec-label').textContent = msg;
  }

  // --- Režim 1: Whisper (server) ---
  if (useWhisper && navigator.mediaDevices && window.MediaRecorder) {
    let recorder = null;
    let chunks = [];
    const pickMime = () => ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']
      .find(t => MediaRecorder.isTypeSupported(t)) || '';

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
          setRecording(false);
          const type = recorder.mimeType || 'audio/webm';
          const ext = type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm';
          processAudio(new Blob(chunks, { type }), 'nahravka.' + ext);
        };
        recorder.start();
        setRecording(true);
        showResult('');
        setStatus('🔴 Nahrávám… klepnutím ukončíte.');
      } catch (e) {
        setStatus('Mikrofon není dostupný: ' + e.message);
      }
    });
    return;
  }

  // --- Režim 2: přepis v prohlížeči ---
  if (!SpeechRecognition) {
    disableMic('Tento prohlížeč neumí přepis řeči. Použijte Chrome, Edge nebo Safari – nebo napište text níže.');
    return;
  }

  let rec = null;
  let listening = false;
  let stoppedByUser = false;
  let finalText = '';

  recBtn.addEventListener('click', () => {
    if (listening) { stoppedByUser = true; rec.stop(); return; }
    rec = new SpeechRecognition();
    rec.lang = 'cs-CZ';
    rec.continuous = true;
    rec.interimResults = true;
    finalText = '';
    stoppedByUser = false;

    rec.onstart = () => {
      listening = true;
      setRecording(true);
      showResult('');
      setStatus('🔴 Poslouchám… mluvte, pak klepněte na tlačítko.');
    };
    rec.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += r[0].transcript + ' ';
        else interim += r[0].transcript;
      }
      freeText.value = (finalText + interim).trim();
    };
    rec.onerror = (e) => {
      const msgs = {
        'not-allowed': 'Přístup k mikrofonu byl zamítnut. Povolte ho v nastavení prohlížeče.',
        'service-not-allowed': 'Přístup k mikrofonu byl zamítnut. Povolte ho v nastavení prohlížeče.',
        'no-speech': 'Nic jsem neslyšel(a) – zkuste to znovu.',
        'audio-capture': 'Mikrofon nebyl nalezen.',
        'network': 'Přepis řeči potřebuje připojení k internetu.',
      };
      showResult('❌ ' + (msgs[e.error] || ('Chyba rozpoznávání: ' + e.error)), 'danger');
    };
    rec.onend = () => {
      listening = false;
      setRecording(false);
      setStatus('');
      // Prohlížeč může poslech ukončit sám po delší pauze – výsledek zpracujeme stejně
      if (freeText.value.trim()) afterTranscript();
      else if (stoppedByUser) showResult('Nic se nezachytilo – zkuste to znovu.', 'warning');
    };
    try {
      rec.start();
    } catch (err) {
      showResult('❌ Nahrávání nelze spustit: ' + err.message, 'danger');
    }
  });
})();
