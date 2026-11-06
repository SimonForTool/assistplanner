/**
 * Syncho → Google kalendář
 *
 * Instalace (v Google účtu, do jehož kalendáře se mají úkoly zapisovat):
 *  1. https://script.google.com → Nový projekt → vložte celý tento soubor.
 *  2. Níže nastavte SECRET na stejný dlouhý náhodný řetězec jako GCAL_SECRET v .env aplikace.
 *  3. Vlevo „Služby“ (+) → Google Calendar API → Přidat (identifikátor ponechte „Calendar“).
 *  4. Nasadit → Nové nasazení → typ „Webová aplikace“:
 *       Spustit jako: Já · Kdo má přístup: Kdokoli  → Nasadit → povolit přístup ke kalendáři.
 *  5. Zkopírujte „URL webové aplikace“ (končí /exec) do GCAL_SCRIPT_URL v .env.
 * Po úpravě skriptu: Implementovat → Spravovat implementace → ✏️ upravit → Verze: Nová verze
 *   → Implementovat (URL zůstává stejná; Google si může znovu vyžádat povolení – nově i pro e-mail).
 */
const SECRET = 'SEM-VLOZTE-STEJNY-TAJNY-KLIC-JAKO-GCAL_SECRET';
const CALENDAR_ID = 'primary';  // hlavní kalendář účtu
const VERSION = 2;              // verze skriptu, kterou aplikace očekává

/** Kontrola v prohlížeči: otevřete URL webové aplikace (…/exec) – ukáže verzi nasazeného skriptu. */
function doGet() {
  return out_({ ok: true, app: 'Syncho', version: VERSION, actions: ['ping', 'upsert', 'delete', 'mail'],
                secretSet: SECRET.indexOf('SEM-VLOZTE') !== 0 });
}

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    if (data.secret !== SECRET) return out_({ ok: false, error: 'unauthorized' });
    if (data.action === 'ping') {
      return out_({ ok: true, calendar: CalendarApp.getDefaultCalendar().getName(), version: VERSION });
    }
    if (data.action === 'delete') {
      try {
        // sendUpdates: 'all' → hosté (např. v Outlooku) dostanou zrušení
        Calendar.Events.remove(CALENDAR_ID, data.eventId, { sendUpdates: 'all' });
      } catch (err) {
        if (!/not found|deleted|404|410/i.test(String(err))) throw err;
      }
      return out_({ ok: true });
    }
    if (data.action === 'upsert') {
      const resource = {
        summary: data.title,
        location: data.location || '',
        description: data.description || '',
        start: { dateTime: data.start, timeZone: data.timeZone },
        end: { dateTime: data.end, timeZone: data.timeZone },
      };
      if (data.eventId) {
        try {
          // patch nemění seznam hostů – ručně pozvaní zůstanou a dostanou aktualizaci
          const ev = Calendar.Events.patch(resource, CALENDAR_ID, data.eventId, { sendUpdates: 'all' });
          if (ev.status !== 'cancelled') return out_({ ok: true, eventId: ev.id });
        } catch (err) {
          if (!/not found|deleted|404|410/i.test(String(err))) throw err;
        }
      }
      // nová událost (nebo původní byla v kalendáři ručně smazána)
      const guests = (data.guests || []).filter(String);
      if (guests.length) resource.attendees = guests.map(function (g) { return { email: g }; });
      const created = Calendar.Events.insert(resource, CALENDAR_ID, { sendUpdates: guests.length ? 'all' : 'none' });
      return out_({ ok: true, eventId: created.id });
    }
    if (data.action === 'mail') {
      // e-mail z tohoto Google účtu (bez SMTP); denní limit Gmailu cca 100 příjemců
      MailApp.sendEmail({ to: data.to, subject: data.subject, body: data.body, name: data.name || 'Syncho' });
      return out_({ ok: true });
    }
    return out_({ ok: false, error: 'neznámá akce' });
  } catch (err) {
    return out_({ ok: false, error: String(err) });
  }
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
