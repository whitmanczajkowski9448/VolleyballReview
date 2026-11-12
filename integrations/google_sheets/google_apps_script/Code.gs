/**
 * VolleyReview SIMPLE Play Library.
 * Bound to a Google Sheet. All grading fields are intentionally excluded.
 * Add Finder.gs in the same Apps Script project for Find & Import.
 */
const V={
  tabs:['All Plays','Saved Plays','Challenges','Faults','POIs',
        'Touch','In-Out','Net','Attack Line','Service-Center Line','Other-Uncategorized'],
  fixed:['Download ZIP','Watch Video','Play ID','New Comment','Latest Comment','Comments','Date','Conference','Match','Type','Category','Set','Score','Play #'],
  end:['Tags']
};

function onOpen(){
  SpreadsheetApp.getUi().createMenu('VolleyReview')
    .addItem('1. Configure backend','configureBackend')
    .addItem('2. Refresh all plays','syncNow')
    .addItem('3. Enable automatic refresh and comments','installTriggers')
    .addSeparator()
    .addItem('Add comment to selected play','addCommentToSelectedPlay')
    .addItem('Open Comments Log','openCommentsLog')
    .addSeparator()
    .addItem('Find & Import: open chooser','openFinder')
    .addItem('Find & Import: search matches','findDvsportMatches')
    .addItem('Find & Import: list plays','loadDvsportPlays')
    .addItem('Find & Import: import play','importSelectedPlay')
    .addToUi();
}
function configureBackend(){
  const ui=SpreadsheetApp.getUi();
  const base=ui.prompt('Integration API','Paste the HTTPS base URL of your deployed VolleyReview API:',ui.ButtonSet.OK_CANCEL);
  if(base.getSelectedButton()!==ui.Button.OK)return;
  const url=base.getResponseText().trim().replace(new RegExp('/+$'),'');
  if(!url.startsWith('https://') || !url.slice(8) || url.slice(8).includes('/')){
    ui.alert('Enter an HTTPS origin with no path.');return;
  }
  const keyPrompt=ui.prompt('Integration key','Paste the separate SHEETS_INTEGRATION_KEY. NEVER use your Supabase service-role key.',ui.ButtonSet.OK_CANCEL);
  if(keyPrompt.getSelectedButton()!==ui.Button.OK)return;
  const key=keyPrompt.getResponseText().trim();
  if(key.length<24){ui.alert('Use a random key with at least 24 characters.');return;}
  PropertiesService.getScriptProperties().setProperties({VR_BASE_URL:url,VR_INTEGRATION_KEY:key});
  ui.alert('Configured. Choose VolleyReview > Refresh all plays.');
}
function request_(method,path,payload){
  const props=PropertiesService.getScriptProperties();
  const base=props.getProperty('VR_BASE_URL');
  const key=props.getProperty('VR_INTEGRATION_KEY');
  if(!base||!key)throw Error('Configure the backend from the VolleyReview menu first.');
  const options={method:method,headers:{'X-Integration-Key':key},muteHttpExceptions:true,followRedirects:false};
  if(payload!==undefined){options.contentType='application/json';options.payload=JSON.stringify(payload);}
  const res=UrlFetchApp.fetch(base+path,options);
  const status=res.getResponseCode(),body=res.getContentText();
  if(status<200||status>=300)throw Error('API HTTP '+status+': '+body.slice(0,350));
  return JSON.parse(body);
}
function getAll_(kind){
  let offset=0;const out=[];
  for(let i=0;i<500;i++){
    const res=request_('get','/api/v1/'+kind+'?offset='+offset+'&limit=200');
    out.push(...(res[kind]||[]));
    if(res.next_offset===null||res.next_offset===undefined)return out;
    if(res.next_offset<=offset)throw Error('Invalid paging token');
    offset=res.next_offset;
  }
  throw Error('Too many plays to sync in one run');
}
function ensureSheet_(book,name){return book.getSheetByName(name)||book.insertSheet(name);}
function text_(v){
  if(v===null||v===undefined)return '';
  if(v===true)return 'Yes';if(v===false)return 'No';
  const s=String(v);return /^[=+@-]/.test(s)?"'"+s:s;
}
function link_(url,label){
  if(!String(url||'').startsWith('https://'))return '';
  const esc=s=>String(s||'').replace(/"/g,'""').replace(/[\\r\\n]/g,' ');
  return '=HYPERLINK("'+esc(url)+'","'+esc(label)+'")';
}
function tabMatch_(tab,p){
  if(tab==='All Plays')return true;
  if(tab==='Saved Plays')return p.play_type==='Saved';
  if(tab==='Challenges')return p.play_type==='Challenge';
  if(tab==='Faults')return p.play_type==='Fault';
  if(tab==='POIs')return p.play_type==='POI';
  const map={'Touch':'Touch','In-Out':'In/Out','Net':'Net',
             'Attack Line':'Attack Line','Service-Center Line':'Service Line / CenterLine'};
  if(map[tab])return p.category===map[tab];
  return !Object.values(map).includes(p.category);
}
function commentIndex_(comments){
  const out={};
  comments.forEach(c=>{
    const key=String(c.play_id);
    if(!out[key])out[key]={count:0,latest:c};
    out[key].count++;
  });
  return out;
}
function drafts_(book){
  const drafts={};
  V.tabs.forEach(tab=>{
    const sh=book.getSheetByName(tab);
    if(!sh||sh.getLastRow()<5)return;
    const head=sh.getRange(4,1,1,sh.getLastColumn()).getValues()[0];
    const col=head.indexOf('New Comment')+1;
    if(!col)return;
    const rows=sh.getLastRow()-4;
    const ids=sh.getRange(5,3,rows,1).getDisplayValues();
    const values=sh.getRange(5,col,rows,1).getValues();
    const saved={};
    ids.forEach((row,i)=>{
      const id=String(row[0]||'').trim(),txt=String(values[i][0]||'').trim();
      if(id&&txt)saved[id]=txt;
    });
    drafts[tab]=saved;
  });
  return drafts;
}
function renderView_(book,tab,plays,index,angles,time,drafts){
  const sh=ensureSheet_(book,tab);
  const filtered=plays.filter(p=>tabMatch_(tab,p));
  const headings=V.fixed.concat(Array.from({length:angles},(_,i)=>'Angle '+(i+1)),V.end);
  const rows=filtered.map(p=>{
    const c=index[String(p.id)]||{count:0,latest:null};
    const first=(p.angles||[])[0];
    const record=[link_(p.download_url,'Download all'),first?link_(first.url,'Watch'):'',
      text_(p.id),(drafts||{})[String(p.id)]||'',
      c.latest?text_(c.latest.comment_text):'',c.count,
      text_(p.match_date),text_(p.conference),text_(p.match_name),
      text_(p.play_type),text_(p.category),text_(p.set_number),text_(p.score),
      text_(p.dvsport_play_number)];
    for(let i=0;i<angles;i++){
      const a=(p.angles||[])[i];
      record.push(a?link_(a.url,a.name||('Angle '+(i+1))):'');
    }
    record.push(c.latest?text_((c.latest.tags||[]).join(', ')):'');
    return record;
  });
  const currentFilter=sh.getFilter();if(currentFilter)currentFilter.remove();
  sh.getDataRange().breakApart();sh.clear();
  const n=headings.length;
  if(sh.getMaxColumns()<n)sh.insertColumnsAfter(sh.getMaxColumns(),n-sh.getMaxColumns());
  if(sh.getMaxRows()<rows.length+4)sh.insertRowsAfter(sh.getMaxRows(),rows.length+4-sh.getMaxRows());
  sh.getRange(1,1,1,n).setBackground('#E8EEF1');
  sh.getRange('A1').setValue('VOLLEYREVIEW · '+tab.toUpperCase()).setFontSize(16).setFontWeight('bold');
  sh.getRange('A2').setValue(filtered.length+' plays · Last refresh '+time);
  sh.getRange(4,1,1,n).setValues([headings]).setBackground('#DDE4E8').setFontWeight('bold').setWrap(true);
  sh.setRowHeight(4,38);
  if(rows.length){
    sh.getRange(5,1,rows.length,n).setValues(rows).setVerticalAlignment('middle');
    sh.getRange(5,1,rows.length,2).setFontColor('#1867A3');
    sh.getRange(5,V.fixed.length+1,rows.length,angles).setFontColor('#1867A3');
    sh.getRange(5,headings.indexOf('New Comment')+1,rows.length,1).setBackground('#FFF4DA');
    sh.getRange(4,1,rows.length+1,n).createFilter();
  }
  sh.getRange(4,headings.indexOf('New Comment')+1).setNote('Enter a comment in the yellow cell and press Enter. First enable the automatic comment trigger.');
  sh.setFrozenRows(4);sh.setFrozenColumns(4);
  sh.setColumnWidth(1,130);sh.setColumnWidth(2,110);sh.setColumnWidth(3,125);
  sh.setColumnWidth(4,330);sh.setColumnWidth(5,380);sh.setColumnWidth(6,100);
  sh.setColumnWidth(7,110);sh.setColumnWidth(8,130);sh.setColumnWidth(9,285);
  sh.setColumnWidths(10,5,105);
  sh.setColumnWidths(V.fixed.length+1,angles,155);
  sh.setColumnWidth(headings.indexOf('Latest Comment')+1,380);
  sh.setColumnWidth(headings.indexOf('New Comment')+1,330);
  sh.setColumnWidth(headings.indexOf('Tags')+1,175);
}
function renderComments_(book,comments,plays){
  const sh=ensureSheet_(book,'Comments Log'),byId={};
  plays.forEach(p=>byId[String(p.id)]=p);
  const head=['Date','Match','Conference','Play #','Play ID','Author','Comment','Tags','Saved At'];
  const rows=comments.map(c=>{
    const p=byId[String(c.play_id)]||{};
    return [text_(p.match_date),text_(p.match_name),text_(p.conference),
      text_(p.dvsport_play_number),text_(c.play_id),text_(c.author),
      text_(c.comment_text),text_((c.tags||[]).join(', ')),text_(c.created_at)];
  });
  const filter=sh.getFilter();if(filter)filter.remove();
  sh.getDataRange().breakApart();sh.clear();
  if(sh.getMaxRows()<rows.length+4)sh.insertRowsAfter(sh.getMaxRows(),rows.length+4-sh.getMaxRows());
  sh.getRange('A1').setValue('ALL PLAY COMMENTS').setFontSize(16).setFontWeight('bold');
  sh.getRange('A2').setValue('Searchable comment history, linked to permanent play IDs.');
  sh.getRange(4,1,1,head.length).setValues([head]).setBackground('#DDE4E8').setFontWeight('bold');
  if(rows.length){
    sh.getRange(5,1,rows.length,head.length).setValues(rows);
    sh.getRange(4,1,rows.length+1,head.length).createFilter();
  }
  sh.setFrozenRows(4);sh.setColumnWidth(2,275);
  sh.setColumnWidth(5,215);sh.setColumnWidth(7,510);sh.setColumnWidth(8,200);
}
function renderGuide_(book,total,comments,time){
  const sh=ensureSheet_(book,'START HERE');
  sh.getDataRange().breakApart();sh.clear();
  sh.getRange('A1:B2').merge().setBackground('#E8EEF1').setFontSize(19).setFontWeight('bold');
  sh.getRange('A1').setValue('VOLLEYREVIEW · PLAY LIBRARY');
  sh.getRange('A4:B12').setValues([
    ['PLAYS',String(total)+' plays'],
    ['COMMENTS',String(comments)+' comments'],
    ['LAST REFRESH',time],
    ['WATCH','Open a play tab. Click Watch or a named camera angle.'],
    ['DOWNLOAD','Click Download all for a ZIP of available camera angles.'],
    ['COMMENT','Enter text into the yellow New Comment cell and press Enter.'],
    ['FIND & IMPORT','Open the Find & Import tab; search by date/conference/teams, choose a match and PLAY #.'],
    ['SAVED PLAYS','A newly imported non-flagged play appears under Saved Plays.'],
    ['NO GRADING','Only videos, play details and comments are shown.']
  ]);
  sh.getRange('A4:A12').setBackground('#EDF2F4').setFontWeight('bold');
  sh.getRange('B4:B12').setWrap(true);
  sh.setColumnWidth(1,190);sh.setColumnWidth(2,700);
  sh.setRowHeights(7,6,48);
}
function syncNow(){
  const lock=LockService.getDocumentLock();
  if(!lock.tryLock(20000))throw Error('A VolleyReview operation is already running');
  try{
    const plays=getAll_('plays'),comments=getAll_('comments'),book=SpreadsheetApp.getActiveSpreadsheet();
    const draft=drafts_(book),index=commentIndex_(comments);
    const maxAngles=Math.max(1,...plays.map(p=>Math.min((p.angles||[]).length,30)));
    const time=Utilities.formatDate(new Date(),book.getSpreadsheetTimeZone(),'yyyy-MM-dd HH:mm');
    V.tabs.forEach(tab=>renderView_(book,tab,plays,index,maxAngles,time,draft[tab]));
    renderComments_(book,comments,plays);renderGuide_(book,plays.length,comments.length,time);
    book.toast('Loaded '+plays.length+' plays and '+comments.length+' comments','VolleyReview',6);
  }finally{lock.releaseLock();}
}
function installTriggers(){
  ScriptApp.getProjectTriggers().forEach(t=>{
    if(['syncNow','handleCommentEdit'].includes(t.getHandlerFunction()))ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('syncNow').timeBased().everyMinutes(15).create();
  ScriptApp.newTrigger('handleCommentEdit').forSpreadsheet(SpreadsheetApp.getActive()).onEdit().create();
  SpreadsheetApp.getUi().alert('Automatic refresh and comment saving enabled.');
}
function saveComment_(playId,message){
  const text=String(message||'').trim();
  if(!text)return;
  if(text.length>4000)throw Error('Max comment length is 4,000 characters');
  const author=Session.getActiveUser().getEmail()||'Sheet reviewer';
  const created=request_('post','/api/v1/plays/'+encodeURIComponent(playId)+'/comments',
    {comment_text:text,author:author,source:'Google Sheets'});
  try{
    const book=SpreadsheetApp.getActiveSpreadsheet();
    V.tabs.forEach(tab=>{
      const sh=book.getSheetByName(tab);
      if(!sh||sh.getLastRow()<5)return;
      const head=sh.getRange(4,1,1,sh.getLastColumn()).getValues()[0];
      const col=head.indexOf('Latest Comment')+1,count=head.indexOf('Comments')+1;
      const hit=sh.getRange(5,3,sh.getLastRow()-4,1).createTextFinder(String(playId)).matchEntireCell(true).findNext();
      if(!hit)return;
      const r=hit.getRow();
      sh.getRange(r,col).setValue(text_(created.comment_text));
      sh.getRange(r,count).setValue(Number(sh.getRange(r,count).getValue()||0)+1);
      sh.getRange(r,head.indexOf('Tags')+1).setValue((created.tags||[]).join(', '));
    });
    book.toast('Comment saved to Supabase','VolleyReview',4);
  }catch(displayError){console.error('Comment saved but view update failed',displayError);}
  return created;
}
function handleCommentEdit(e){
  if(!e||!e.range)return;
  if(e.range.getSheet().getName()==='Find & Import'){handleFinderEdit(e);return;}
  const sh=e.range.getSheet();
  if(!V.tabs.includes(sh.getName())||e.range.getLastRow()<5)return;
  const head=sh.getRange(4,1,1,sh.getLastColumn()).getValues()[0];
  const col=head.indexOf('New Comment')+1;
  if(!col||e.range.getColumn()>col||e.range.getLastColumn()<col)return;
  const lock=LockService.getDocumentLock();
  if(!lock.tryLock(20000))throw Error('A VolleyReview operation is in progress');
  try{
    for(let r=Math.max(5,e.range.getRow());r<=e.range.getLastRow();r++){
      const cell=sh.getRange(r,col),msg=String(cell.getValue()||'').trim();
      if(!msg)continue;
      const id=String(sh.getRange(r,3).getValue()||'').trim();
      if(!id){cell.setNote('Missing play ID');continue;}
      try{saveComment_(id,msg);cell.clearContent();cell.setNote('Saved to Supabase at '+new Date());}
      catch(err){cell.setNote('NOT SAVED: '+err.message);}
    }
  }finally{lock.releaseLock();}
}
function addCommentToSelectedPlay(){
  const ui=SpreadsheetApp.getUi(),sh=SpreadsheetApp.getActiveSheet();
  const row=sh.getActiveCell().getRow();
  if(!V.tabs.includes(sh.getName())||row<5){ui.alert('Select a play row first');return;}
  const id=String(sh.getRange(row,3).getValue()||'').trim();
  if(!id){ui.alert('Missing play ID');return;}
  const prompt=ui.prompt('Comment','Enter a comment for this play:',ui.ButtonSet.OK_CANCEL);
  if(prompt.getSelectedButton()!==ui.Button.OK||!prompt.getResponseText().trim())return;
  try{saveComment_(id,prompt.getResponseText());}catch(err){ui.alert('Could not save comment: '+err.message);}
}
function openCommentsLog(){
  const book=SpreadsheetApp.getActiveSpreadsheet();
  book.setActiveSheet(ensureSheet_(book,'Comments Log'));
}
