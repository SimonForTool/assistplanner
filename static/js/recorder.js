// Hlasové zadání → automatické vyplnění formuláře.
// S OpenAI (data-whisper="1"): nahrávka přes MediaRecorder → Whisper + GPT na serveru.
// Bez OpenAI: přepis řeči přímo v prohlížeči (Web Speech API, čeština) → pravidlový rozbor na serveru.
(function () {
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const recBtn = document.getElementById('rec-btn');
  const fileInput = document.getElementById('audio-file');
  const textBtn = document.getElementById('ai-text-btn');
  const freeText = document.getElementById('free-text');
  const statusEl = document.getElementById('rec-status');
  const resultEl = document.getElementById('ai-result');
  const useWhisper = recBtn && recBtn.dataset.whisper === '1';
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
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
    recBtn.setAttribute('aria-label', on ? 'Zastavit a vyplnit' : 'Nahrávat');
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
    // Na telefonu posuneme na vyplněný formulář
    if (window.innerWidth < 992) form.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function send(formData) {
    if (busy) return;
    busy = true;
    showResult('');
    setStatus('⏳ Vyplňuji údaje…');
    textBtn.disabled = true;
    if (recBtn) recBtn.disabled = true;
    try {
      const r = await fetch(window.AI_EXTRACT_URL, {
        method: 'POST', body: formData, headers: { 'X-CSRF-Token': csrf },
      });
      const data = await r.json().catch(() => ({ error: 'Neplatná odpověď serveru (' + r.status + ').' }));
      if (!r.ok || data.error) throw new Error(data.error || ('Chyba ' + r.status));
      if (data.transcript) freeText.value = data.transcript;
      fillForm(data.fields);
      showResult(data.ai_used ? '✅ Vyplněno pomocí AI – zkontrolujte a uložte.'
                              : '✅ Vyplněno automaticky – zkontrolujte údaje a uložte.', 'success');
    } catch (e) {
      showResult('❌ ' + e.message, 'danger');
    } finally {
      busy = false;
      setStatus('');
      textBtn.disabled = false;
      if (recBtn && !recBtn.hasAttribute('data-disabled')) recBtn.disabled = false;
    }
  }

  function sendText(text) {
    const fd = new FormData();
    fd.append('text', text);
    send(fd);
  }

  textBtn.addEventListener('click', () => {
    const text = freeText.value.trim();
    if (!text) { showResult('Napište nebo nadiktujte nejdřív text.', 'warning'); return; }
    sendText(text);
  });

  if (fileInput) {
    fileInput.addEventListener('change', () => {
      const f = fileInput.files[0];
      if (f) {
        const fd = new FormData();
        fd.append('audio', f, f.name);
        send(fd);
      }
      fileInput.value = '';
    });
  }

  function disableMic(msg) {
    recBtn.disabled = true;
    recBtn.setAttribute('data-disabled', '1');
    document.getElementById('rec-label').textContent = msg;
  }

  if (!recBtn) return;

  // --- Režim 1: Whisper (server) ---
  if (useWhisper) {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      if (SpeechRecognition) return initBrowserSpeech();
      return disableMic('Prohlížeč nepodporuje nahrávání – napište text níže.');
    }
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
          const fd = new FormData();
          fd.append('audio', new Blob(chunks, { type }), 'nahravka.' + ext);
          send(fd);
        };
        recorder.start();
        setRecording(true);
        setStatus('🔴 Nahrávám… klepnutím ukončíte.');
      } catch (e) {
        setStatus('Mikrofon není dostupný: ' + e.message);
      }
    });
    return;
  }

  // --- Režim 2: přepis v prohlížeči ---
  if (!SpeechRecognition) {
    return disableMic('Tento prohlížeč neumí přepis řeči. Použijte Chrome, Edge nebo Safari – nebo napište text níže.');
  }
  initBrowserSpeech();

  function initBrowserSpeech() {
    let rec = null;
    let finalText = '';
    let listening = false;
    let stoppedByUser = false;

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
        const text = freeText.value.trim();
        // Prohlížeč může poslech ukončit sám po delší pauze – výsledek zpracujeme stejně
        if (text) sendText(text);
        else if (stoppedByUser) showResult('Nic se nezachytilo – zkuste to znovu.', 'warning');
      };
      try {
        rec.start();
      } catch (err) {
        showResult('❌ Nahrávání nelze spustit: ' + err.message, 'danger');
      }
    });
  }
})();
