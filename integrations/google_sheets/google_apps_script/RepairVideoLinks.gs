/**
 * VolleyReview live-sheet video link repair.
 * Repairs hyperlinks only in "All Plays"; category tabs that FILTER it update automatically.
 * Preserves comments, checkboxes, play metadata, ZIPs, rows and formatting.
 *
 * One-time setup: paste this file into the existing bound Apps Script project,
 * then run vrRepairVideoLinks() from the editor. Existing script properties:
 * VR_BASE_URL and VR_INTEGRATION_KEY must be configured.
 */
function vrRepairVideoLinks() {
  const book = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = book.getSheetByName('All Plays');
  if (!sheet) throw Error('Could not find the All Plays tab.');
  const props = PropertiesService.getScriptProperties();
  const base = String(props.getProperty('VR_BASE_URL') || '').replace(/\/+$/, '');
  const key = String(props.getProperty('VR_INTEGRATION_KEY') || '');
  if (!/^https:\/\//.test(base) || !key) {
    throw Error('Missing VolleyReview backend configuration. First configure the backend in the VolleyReview menu.');
  }

  const health = UrlFetchApp.fetch(base + '/health', {muteHttpExceptions:true});
  if (health.getResponseCode() !== 200) throw Error('VolleyReview Render API is not reachable (HTTP ' + health.getResponseCode() + ').');
  const diagnostics = JSON.parse(health.getContentText());
  if (diagnostics.dvSportVideoSigningConfigured === false)
    throw Error('Render is missing DVSPORT_COOKIE. Configure your authorized FilmRoom session cookie on Render before repairing links.');
  if (diagnostics.allowedMediaHostsConfigured === false)
    throw Error('Render is missing ALLOWED_MEDIA_HOSTS. Configure the 5 DV Sport replay Azure hostnames before repairing links.');

  const headerRow = 4;
  const headers = sheet.getRange(headerRow, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
  const idColumn = headers.indexOf('Play ID') + 1;
  const watchColumn = headers.indexOf('Watch Video') + 1;
  const angles = [];
  headers.forEach(function(name, index) {
    const match = /^Angle\s+(\d+)$/i.exec(String(name || '').trim());
    if (match) angles.push({column:index + 1,index:Number(match[1]) - 1});
  });
  if (!idColumn || !watchColumn || !angles.length)
    throw Error('Expected Play ID, Watch Video and Angle columns in All Plays row 4.');
  const firstAngleCol = Math.min.apply(null, angles.map(a => a.column));
  const lastAngleCol = Math.max.apply(null, angles.map(a => a.column));
  const rowCount = sheet.getLastRow() - headerRow;
  if (rowCount < 1) throw Error('All Plays has no records.');

  const byId = {};
  let offset = 0;
  for (let page = 0; page < 300; page++) {
    const url = base + '/api/v1/plays?offset=' + offset + '&limit=200';
    const response = UrlFetchApp.fetch(url, {
      method:'get', headers:{'X-Integration-Key':key}, muteHttpExceptions:true
    });
    if (response.getResponseCode() !== 200)
      throw Error('Could not get authorized video links from Render (HTTP ' + response.getResponseCode() + '): ' + response.getContentText().slice(0,160));
    const data = JSON.parse(response.getContentText());
    (data.plays || []).forEach(function(play) { byId[String(play.id)] = play; });
    if (data.next_offset == null) break;
    if (data.next_offset <= offset) throw Error('Invalid API pagination response');
    offset = data.next_offset;
    if (page === 299) throw Error('API returned too many pages');
  }

  const ids = sheet.getRange(5,idColumn,rowCount,1).getDisplayValues();
  const watchFormulas = sheet.getRange(5,watchColumn,rowCount,1).getFormulas();
  const angleFormulas = sheet.getRange(5,firstAngleCol,rowCount,lastAngleCol-firstAngleCol+1).getFormulas();
  const makeLink = function(url,label) {
    if (!/^https:\/\//.test(String(url || ''))) return '';
    const clean = s => String(s).replace(/"/g,'""').replace(/[\r\n]/g,' ');
    return '=HYPERLINK("' + clean(url) + '","' + clean(label) + '")';
  };
  let repaired = 0, unmatched = 0, repairedAngles = 0;
  ids.forEach(function(rec,r) {
    const id = String(rec[0] || '').trim();
    if (!id) return;
    const play = byId[id];
    if (!play) { unmatched++; return; }
    const video = play.angles || [];
    if (!video.length) return;
    watchFormulas[r][0] = makeLink(video[0].url,'▶ Watch');
    angles.forEach(function(entry) {
      const angle = video[entry.index];
      angleFormulas[r][entry.column-firstAngleCol] = angle ? makeLink(angle.url,'▶ ' + (angle.name || ('Angle ' + (entry.index+1)))) : '';
      if (angle) repairedAngles++;
    });
    repaired++;
  });
  // Only the two hyperlink areas are written; all other cells remain untouched.
  sheet.getRange(5,watchColumn,rowCount,1).setFormulas(watchFormulas);
  sheet.getRange(5,firstAngleCol,rowCount,lastAngleCol-firstAngleCol+1).setFormulas(angleFormulas);
  SpreadsheetApp.flush();
  const message = 'Repaired ' + repaired + ' plays and ' + repairedAngles + ' camera links.' +
    (unmatched ? ' ' + unmatched + ' play IDs were not found in the API and were left unchanged.' : '');
  book.toast(message,'VolleyReview',10);
  Logger.log(message);
  return message;
}
