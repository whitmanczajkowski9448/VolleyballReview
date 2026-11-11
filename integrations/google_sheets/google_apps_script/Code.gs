/**
 * VolleyReview Master Play Library — paste into Extensions > Apps Script.
 * Converts a normal Google Sheet into a synced, comment-enabled play library.
 * NO SUPABASE SERVICE KEY belongs in this file. The only key here is the
 * limited VolleyReview backend integration key (stored as Script Property).
 */
const V = {
  types: ['All Plays', 'Challenges', 'Faults', 'POIs'],
  categories: ['Touch', 'In-Out', 'Net', 'Attack Line', 'Service-Center Line', 'Other-Uncategorized'],
  color: {navy: '#122B41', teal: '#007C85', pale: '#EAF3F6', cream: '#FFF4DA', ink: '#203447', white: '#FFFFFF'},
  fixed: [
    'Download ZIP', 'View Play', 'Play ID', 'Match Date', 'Conference', 'Match',
    'Play Type', 'Category', 'Set', 'Score', 'Challenging Team',
    'Original Call', 'Challenge Outcome', 'Outcome Detail', 'Referee Judgment',
    'Review Status', 'Review Length', 'Starred', 'DV Sport Category', 'DV Sport Result'
  ],
  end: [
    'Latest Comment', 'Comment Count', 'New Comment', 'Comment Tags',
    'Training Use', 'Reviewer Notes', 'Weekly Summary Note', 'Last Sync',
    'DV Sport Play #', 'DV Sport ID'
  ]
};

function onOpen() {
  SpreadsheetApp.getUi().createMenu('VolleyReview')
    .addItem('1. Configure backend', 'configureBackend')
    .addItem('2. Refresh all plays', 'syncNow')
    .addItem('3. Enable automatic syncing + comments', 'installTriggers')
    .addSeparator()
    .addItem('Add comment to selected play', 'addCommentToSelectedPlay')
    .addItem('Open Comments Log', 'openCommentsLog')
    .addToUi();
}

function configureBackend() {
  const ui = SpreadsheetApp.getUi();
  const base = ui.prompt('VolleyReview backend', 'Paste the HTTPS base URL for your deployed integration API:', ui.ButtonSet.OK_CANCEL);
  if (base.getSelectedButton() !== ui.Button.OK) return;
  const url = base.getResponseText().trim().replace(/\/+$/, '');
  if (!/^https:\/\/[\w.-]+(?::\d+)?$/.test(url)) {
    ui.alert('Please enter only your HTTPS backend origin, for example https://review-api.example.com'); return;
  }
  const keyPrompt = ui.prompt('Integration key', 'Paste the SHEETS_INTEGRATION_KEY configured on the backend. Do NOT use a Supabase API key:', ui.ButtonSet.OK_CANCEL);
  if (keyPrompt.getSelectedButton() !== ui.Button.OK) return;
  const key = keyPrompt.getResponseText().trim();
  if (key.length < 24) { ui.alert('Use a random key at least 24 characters long.'); return; }
  PropertiesService.getScriptProperties().setProperties({VR_BASE_URL: url, VR_INTEGRATION_KEY: key});
  ui.alert('Configured. Next choose VolleyReview > Refresh all plays.');
}

function cfg_() {
  const props = PropertiesService.getScriptProperties();
  const base = props.getProperty('VR_BASE_URL');
  const key = props.getProperty('VR_INTEGRATION_KEY');
  if (!base || !key) throw Error('Configure the backend from the VolleyReview menu first.');
  return {base, key};
}

function request_(method, path, obj) {
  const c = cfg_();
  const options = {
    method: method,
    headers: {'X-Integration-Key': c.key},
    muteHttpExceptions: true,
    followRedirects: false
  };
  if (obj !== undefined) {
    options.contentType = 'application/json';
    options.payload = JSON.stringify(obj);
  }
  const response = UrlFetchApp.fetch(c.base + path, options);
  const status = response.getResponseCode();
  const body = response.getContentText();
  if (status < 200 || status >= 300) throw Error('VolleyReview API HTTP ' + status + ': ' + body.substring(0, 350));
  return JSON.parse(body);
}

function getAll_(resource, field) {
  let offset = 0;
  const rows = [];
  for (let page = 0; page < 500; page++) {
    const chunk = request_('get', '/api/v1/' + resource + '?offset=' + offset + '&limit=200');
    rows.push(...(chunk[field] || []));
    if (chunk.next_offset === null || chunk.next_offset === undefined) return rows;
    if (chunk.next_offset <= offset) throw Error('Invalid pagination cursor');
    offset = chunk.next_offset;
  }
  throw Error('Too many pages. Please narrow the API dataset.');
}

function text_(val) {
  if (val === null || val === undefined || val === false) return val === false ? 'No' : '';
  if (val === true) return 'Yes';
  const value = String(val);
  // Prevent DV Sport data or user comments from being interpreted as spreadsheet formulas.
  return /^[=+@\-]/.test(value) ? "'" + value : value;
}

function link_(url, label) {
  if (!/^https:\/\//i.test(url || '')) return '';
  const escape = s => String(s || '').replace(/"/g, '""').replace(/[\r\n]+/g, ' ');
  return '=HYPERLINK("' + escape(url) + '","' + escape(label) + '")';
}

function fmtSeconds_(val) {
  if (val === null || val === '' || val === undefined || isNaN(Number(val))) return '';
  const s = Math.round(Number(val));
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

function tabMatches_(name, p) {
  if (name === 'All Plays') return true;
  if (name === 'Challenges') return p.play_type === 'Challenge';
  if (name === 'Faults') return p.play_type === 'Fault';
  if (name === 'POIs') return p.play_type === 'POI';
  if (name === 'Touch') return p.category === 'Touch';
  if (name === 'In-Out') return p.category === 'In/Out';
  if (name === 'Net') return p.category === 'Net';
  if (name === 'Attack Line') return p.category === 'Attack Line';
  if (name === 'Service-Center Line') return p.category === 'Service Line / CenterLine';
  return !['Touch','In/Out','Net','Attack Line','Service Line / CenterLine'].includes(p.category);
}

function ensureSheet_(book, name) {
  return book.getSheetByName(name) || book.insertSheet(name);
}

function buildCommentIndex_(allComments) {
  const out = {};
  allComments.forEach(c => {
    const id = String(c.play_id);
    if (!out[id]) out[id] = {count: 0, latest: null};
    out[id].count++;
    // API returns newest first.
    if (!out[id].latest) out[id].latest = c;
  });
  return out;
}

function sheetRow_(p, maxAngles, cIndex, pendingDraft) {
  const ci = cIndex[String(p.id)] || {count: 0, latest: null};
  const arr = [
    link_(p.download_url, '⬇ Download ZIP'), link_(p.play_url, 'View in VolleyReview'),
    text_(p.id), text_(p.match_date), text_(p.conference), text_(p.match_name),
    text_(p.play_type), text_(p.category), text_(p.set_number), text_(p.score), text_(p.challenging_team),
    text_(p.original_call), text_(p.outcome), text_(p.outcome_detail), text_(p.referee_judgment),
    text_(p.review_status), fmtSeconds_(p.challenge_length_seconds), p.starred ? 'Yes' : 'No',
    text_(p.dvsport_category), text_(p.dvsport_result)
  ];
  for (let i = 0; i < maxAngles; i++) {
    const a = (p.angles || [])[i];
    arr.push(a ? link_(a.url, a.name || ('Angle ' + (i+1))) : '');
  }
  const latest = ci.latest || null;
  arr.push(
    latest ? text_(latest.comment_text) : '', ci.count,
    pendingDraft || '', // NEW COMMENT: drafts are preserved on refresh until saved
    latest ? text_((latest.tags || []).join(', ')) : '',
    p.training ? 'Yes' : 'No', text_(p.reviewer_notes), text_(p.weekly_summary_note),
    new Date().toISOString(), text_(p.dvsport_play_number), text_(p.dvsport_id)
  );
  return arr;
}

function renderView_(book, name, plays, maxAngles, cIndex, time, drafts) {
  const sheet = ensureSheet_(book, name);
  const filtered = plays.filter(p => tabMatches_(name, p));
  const headers = V.fixed.concat(Array.from({length: maxAngles}, (_, i) => 'Angle ' + (i + 1)), V.end);
  const data = filtered.map(p => sheetRow_(p, maxAngles, cIndex, (drafts || {})[String(p.id)]));
  const n = headers.length;
  const filter = sheet.getFilter();
  if (filter) filter.remove();
  sheet.getDataRange().breakApart();
  sheet.clear();
  if (sheet.getMaxColumns() < n) sheet.insertColumnsAfter(sheet.getMaxColumns(), n - sheet.getMaxColumns());
  if (sheet.getMaxRows() < data.length + 4) sheet.insertRowsAfter(sheet.getMaxRows(), data.length + 4 - sheet.getMaxRows());
  sheet.getRange(1, 1, 1, n).setBackground(V.color.navy).setFontColor(V.color.white).setFontWeight('bold');
  sheet.getRange('A1').setValue('VOLLEYREVIEW  /  ' + name.toUpperCase()).setFontSize(16);
  sheet.setRowHeight(1, 37);
  sheet.getRange(2, 1, 1, n).setBackground(V.color.pale).setFontColor(V.color.ink);
  sheet.getRange('A2').setValue(filtered.length + ' plays  •  Last sync: ' + time);
  sheet.getRange(3, 1, 1, n).setBackground(V.color.teal).setFontColor(V.color.white);
  sheet.getRange('A3').setValue('ACTION');
  sheet.getRange('C3').setValue('PLAY DETAILS');
  sheet.getRange(3, 21).setValue('CAMERA ANGLES');
  sheet.getRange(3, 21 + maxAngles).setValue('COMMENTS & FOLLOW-UP');
  sheet.getRange(4, 1, 1, n).setValues([headers]).setBackground(V.color.navy)
    .setFontColor(V.color.white).setFontWeight('bold').setWrap(true);
  sheet.setRowHeight(4, 40);
  if (data.length) {
    const r = sheet.getRange(5, 1, data.length, n);
    r.setValues(data).setVerticalAlignment('middle');
    r.setWrapStrategy(SpreadsheetApp.WrapStrategy.CLIP);
    const editableCol = headers.indexOf('New Comment') + 1;
    sheet.getRange(5, editableCol, data.length, 1).setBackground(V.color.cream);
    sheet.getRange(5, 1, data.length, 2).setFontColor('#1766A8');
    sheet.getRange(5, 21, data.length, maxAngles).setFontColor('#1766A8');
    sheet.getRange(4, 1, data.length + 1, n).createFilter();
    sheet.getRange(4, editableCol).setNote('Type a comment into any yellow cell and press Enter. First enable automatic syncing + comments from the VolleyReview menu. Add #Training, #Rules, or other tags if useful.');
  }
  sheet.setFrozenRows(4);
  sheet.setFrozenColumns(3);
  sheet.setColumnWidth(1, 155);
  sheet.setColumnWidth(2, 153);
  sheet.setColumnWidth(3, 225);
  sheet.setColumnWidth(4, 110);
  sheet.setColumnWidth(5, 155);
  sheet.setColumnWidth(6, 290);
  sheet.setColumnWidths(7, 14, 138);
  sheet.setColumnWidths(21, maxAngles, 155);
  sheet.setColumnWidth(headers.indexOf('Latest Comment') + 1, 420);
  sheet.setColumnWidth(headers.indexOf('New Comment') + 1, 280);
  sheet.setColumnWidth(headers.indexOf('Reviewer Notes') + 1, 325);
  sheet.setColumnWidth(headers.indexOf('Weekly Summary Note') + 1, 325);
  sheet.setTabColor(name === 'All Plays' ? '#1E647A' : V.types.includes(name) ? '#4B91B2' : '#61A799');
}

function renderComments_(book, comments, plays) {
  const sheet = ensureSheet_(book, 'Comments Log');
  const lookup = {};
  plays.forEach(p => lookup[String(p.id)] = p);
  const headers = ['Comment ID','Play ID','Match Date','Conference','Match','Category',
                   'Commented At','Author','Comment','Tags','Training Use','Source','Download ZIP'];
  const rows = comments.map(c => {
    const p = lookup[String(c.play_id)] || {};
    return [text_(c.id), text_(c.play_id), text_(p.match_date), text_(p.conference),
            text_(p.match_name), text_(p.category), text_(c.created_at),
            text_(c.author), text_(c.comment_text), text_((c.tags || []).join(', ')),
            p.training ? 'Yes' : 'No', text_(c.source), link_(p.download_url, '⬇ ZIP')];
  });
  const filter = sheet.getFilter(); if (filter) filter.remove();
  sheet.getDataRange().breakApart(); sheet.clear();
  if (sheet.getMaxColumns() < 13) sheet.insertColumnsAfter(sheet.getMaxColumns(), 13-sheet.getMaxColumns());
  if (sheet.getMaxRows() < rows.length + 4) sheet.insertRowsAfter(sheet.getMaxRows(), rows.length + 4 - sheet.getMaxRows());
  sheet.getRange(1, 1, 1, 13).setBackground(V.color.navy).setFontColor(V.color.white).setFontWeight('bold');
  sheet.getRange('A1').setValue('VOLLEYREVIEW  /  COMMENTS LOG').setFontSize(16);
  sheet.setRowHeight(1, 37);
  sheet.getRange('A2').setValue('All comments are linked to a permanent Play ID. Newest comments first.');
  sheet.getRange(2, 1, 1, 13).setBackground(V.color.pale);
  sheet.getRange(4, 1, 1, 13).setValues([headers]).setBackground(V.color.teal).setFontColor(V.color.white).setFontWeight('bold');
  if (rows.length) {
    sheet.getRange(5, 1, rows.length, 13).setValues(rows).setVerticalAlignment('middle');
    sheet.getRange(4, 1, rows.length + 1, 13).createFilter();
    sheet.getRange(5, 13, rows.length, 1).setFontColor('#1766A8');
  }
  sheet.setFrozenRows(4); sheet.setFrozenColumns(2);
  sheet.setColumnWidths(1, 8, 165); sheet.setColumnWidth(5, 280);
  sheet.setColumnWidth(9, 470); sheet.setColumnWidth(10, 220);
  sheet.setTabColor('#8663A2');
}

function renderGuide_(book, total, comments, maxAngles, time) {
  const sheet = ensureSheet_(book, 'START HERE');
  sheet.getDataRange().breakApart(); sheet.clear();
  sheet.getRange('A1:H2').merge().setBackground(V.color.navy).setFontColor(V.color.white)
    .setFontWeight('bold').setFontSize(18);
  sheet.getRange('A1').setValue('VOLLEYREVIEW  /  MASTER PLAY LIBRARY');
  sheet.getRange('A4:B4').setValues([['STATUS', total + ' plays  •  ' + comments + ' comments  •  ' + maxAngles + ' maximum camera angles']]);
  sheet.getRange('A5:B5').setValues([['LAST SYNC', time]]);
  sheet.getRange('A7:B13').setValues([
    ['1  FIND A PLAY', 'Choose All Plays, Challenges, Faults, POIs, or a classification tab. Filter any column.'],
    ['2  WATCH VIDEO', 'Click the named camera angle link in any play row.'],
    ['3  DOWNLOAD ALL', 'Click Download ZIP at the very beginning of the row. Links refresh during sync.'],
    ['4  ADD A COMMENT', 'Select a row, then VolleyReview > Add comment to selected play; OR type into a yellow New Comment cell.'],
    ['5  TAG COMMENTS', 'Add words such as #Training or #Rules in the comment to make them searchable later.'],
    ['6  FIND YOUR NOTES', 'Comments Log retains the complete history; other tabs display the most recent comment.'],
    ['7  REFRESH', 'Use VolleyReview > Refresh all plays; install an automatic 15-minute refresh in the menu.']
  ]);
  sheet.getRange('A16:B16').setValues([['DATA SAFETY', 'Supabase is the source of truth. Do not edit the imported data columns directly.']]);
  sheet.getRange('A17:B17').setValues([['ZIP ACCESS', 'Signed download links expire; refresh if prompted. Share only with authorized reviewers.']]);
  sheet.getRange('A4:A17').setFontWeight('bold').setBackground(V.color.pale);
  sheet.getRange('B4:B17').setWrap(true);
  sheet.setColumnWidth(1, 200); sheet.setColumnWidth(2, 720); sheet.setRowHeights(7, 7, 45);
  sheet.setTabColor('#122B41');
}

// Keep not-yet-saved comments when a refresh runs after a transient API failure.
function collectDrafts_(book) {
  const output = {};
  V.types.concat(V.categories).forEach(name => {
    const sh = book.getSheetByName(name);
    if (!sh || sh.getLastRow() < 5) return;
    const headers = sh.getRange(4, 1, 1, sh.getLastColumn()).getValues()[0];
    const newCommentCol = headers.indexOf('New Comment') + 1;
    if (!newCommentCol) return;
    const rows = sh.getLastRow() - 4;
    const ids = sh.getRange(5, 3, rows, 1).getDisplayValues();
    const drafts = sh.getRange(5, newCommentCol, rows, 1).getValues();
    const byPlay = {};
    ids.forEach((item, i) => {
      const id = String(item[0] || '').trim();
      const draft = String(drafts[i][0] || '').trim();
      if (id && draft) byPlay[id] = draft;
    });
    output[name] = byPlay;
  });
  return output;
}

function syncNow() {
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(20000)) throw Error('Another VolleyReview operation is in progress.');
  try {
    const plays = getAll_('plays', 'plays');
    const comments = getAll_('comments', 'comments');
    const cIndex = buildCommentIndex_(comments);
    const maxAngles = Math.max(1, ...plays.map(p => Math.min((p.angles || []).length, 30)));
    const book = SpreadsheetApp.getActiveSpreadsheet();
    const drafts = collectDrafts_(book);
    const time = Utilities.formatDate(new Date(), book.getSpreadsheetTimeZone(), 'yyyy-MM-dd HH:mm');
    V.types.concat(V.categories).forEach(name => renderView_(book, name, plays, maxAngles, cIndex, time, drafts[name]));
    renderComments_(book, comments, plays);
    renderGuide_(book, plays.length, comments.length, maxAngles, time);
    book.toast('Updated ' + plays.length + ' plays and ' + comments.length + ' comments', 'VolleyReview', 7);
  } finally {
    lock.releaseLock();
  }
}

function installTriggers() {
  cfg_();
  ScriptApp.getProjectTriggers().forEach(t => {
    if (['syncNow','handleCommentEdit'].includes(t.getHandlerFunction())) ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('syncNow').timeBased().everyMinutes(15).create();
  ScriptApp.newTrigger('handleCommentEdit').forSpreadsheet(SpreadsheetApp.getActive()).onEdit().create();
  SpreadsheetApp.getUi().alert('Enabled: refresh every 15 minutes and save comments when yellow cells are edited.');
}

function saveComment_(playId, message, sheet, row) {
  const text = String(message || '').trim();
  if (!text) return;
  if (text.length > 4000) throw Error('Maximum comment length is 4,000 characters.');
  const author = Session.getActiveUser().getEmail() || 'Google Sheets reviewer';
  const created = request_('post', '/api/v1/plays/' + encodeURIComponent(playId) + '/comments',
    {comment_text: text, author: author, source: 'Google Sheets'});
  try {
    // Update visible summaries on every tab without changing the canonical Play ID.
  const book = SpreadsheetApp.getActiveSpreadsheet();
  V.types.concat(V.categories).forEach(name => {
    const sh = book.getSheetByName(name);
    if (!sh || sh.getLastRow() < 5) return;
    const headers = sh.getRange(4, 1, 1, sh.getLastColumn()).getValues()[0];
    const ccol = headers.indexOf('Latest Comment') + 1;
    const countcol = headers.indexOf('Comment Count') + 1;
    const tagscol = headers.indexOf('Comment Tags') + 1;
    if (!ccol || !countcol) return;
    const hit = sh.getRange(5, 3, sh.getLastRow()-4, 1).createTextFinder(String(playId)).matchEntireCell(true).findNext();
    if (!hit) return;
    const r = hit.getRow();
    sh.getRange(r, ccol).setValue(text_(created.comment_text));
    sh.getRange(r, countcol).setValue(Number(sh.getRange(r, countcol).getValue() || 0) + 1);
    if (tagscol) sh.getRange(r, tagscol).setValue((created.tags || []).join(', '));
  });
  // The periodic refresh rebuilds full comment history (including this new comment).
  book.toast('Comment saved to Supabase for play ' + playId, 'VolleyReview', 5);
  } catch (displayError) {
    console.error('Comment saved, but immediate sheet display refresh failed:', displayError);
  }
  return created;
}

function handleCommentEdit(e) {
  if (!e || !e.range) return;
  const sh = e.range.getSheet();
  if (!V.types.concat(V.categories).includes(sh.getName()) || e.range.getLastRow() < 5) return;
  const headers = sh.getRange(4, 1, 1, sh.getLastColumn()).getValues()[0];
  const commentCol = headers.indexOf('New Comment') + 1;
  if (!commentCol || e.range.getColumn() > commentCol || e.range.getLastColumn() < commentCol) return;
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(20000)) throw Error('Another VolleyReview operation is in progress.');
  try {
    const start = Math.max(5, e.range.getRow());
    const end = e.range.getLastRow();
    for (let r = start; r <= end; r++) {
      const cell = sh.getRange(r, commentCol);
      const msg = String(cell.getValue() || '').trim();
      if (!msg) continue;
      const playId = String(sh.getRange(r, 3).getValue()).trim();
      if (!playId) { cell.setNote('Missing Play ID. Not saved.'); continue; }
      try {
        saveComment_(playId, msg, sh, r);
        cell.clearContent();
        cell.setNote('Saved to Supabase on ' + new Date().toLocaleString());
      } catch (err) {
        cell.setNote('NOT SAVED. ' + err.message + '  •  Try again after fixing the problem.');
        console.error('VolleyReview comment failure:', err);
      }
    }
  } finally { lock.releaseLock(); }
}

function addCommentToSelectedPlay() {
  const ui = SpreadsheetApp.getUi();
  const sh = SpreadsheetApp.getActiveSheet();
  const row = sh.getActiveCell().getRow();
  if (!V.types.concat(V.categories).includes(sh.getName()) || row < 5) {
    ui.alert('First select a play row on a play tab.'); return;
  }
  const playId = String(sh.getRange(row, 3).getValue() || '').trim();
  if (!playId) { ui.alert('No play ID in this row.'); return; }
  const prompt = ui.prompt('Comment on play ' + playId, 'Type your comment. Add #Training, #Rules, etc. for searchable tags:', ui.ButtonSet.OK_CANCEL);
  if (prompt.getSelectedButton() !== ui.Button.OK || !prompt.getResponseText().trim()) return;
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(20000)) { ui.alert('Sync in progress. Try again.'); return; }
  try { saveComment_(playId, prompt.getResponseText().trim(), sh, row); }
  catch (err) { ui.alert('Comment not saved: ' + err.message); }
  finally { lock.releaseLock(); }
}

function openCommentsLog() {
  const book = SpreadsheetApp.getActiveSpreadsheet();
  book.setActiveSheet(ensureSheet_(book, 'Comments Log'));
}
