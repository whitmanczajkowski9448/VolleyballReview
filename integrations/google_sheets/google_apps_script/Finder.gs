/**
 * Find & Import: search authorized DV Sport FULL GAME playlists, choose the
 * numbered play, then save source metadata and all cameras in Supabase.
 * This deliberately does NOT create any grade or reviewer evaluation.
 */
const FIND={name:'Find & Import',cache:'_Finder Data',match:'B11',play:'B14',status:'B17'};

function finderSheet_(){
  const book=SpreadsheetApp.getActiveSpreadsheet();
  const sh=ensureSheet_(book,FIND.name);
  if(sh.getRange('A1').getValue()==='FIND & IMPORT A PLAY')return sh;
  sh.clear();
  sh.getRange('A1:B2').merge().setValue('FIND & IMPORT A PLAY').setFontSize(19).setFontWeight('bold').setBackground('#E8EEF1');
  sh.getRange('A3:B3').merge().setValue('Search by conference, date or teams. Choose the match and DV Sport PLAY #. No grading.');
  sh.getRange('A5:B8').setValues([
    ['Conference','All'],['Team or match search',''],
    ['From date',new Date(Date.now()-21*86400000)],['Through date',new Date()]
  ]);
  sh.getRange('A10:B11').setValues([['STEP 1','VolleyReview > Find & Import: search matches'],['Match','']]);
  sh.getRange('A13:B14').setValues([['STEP 2','Select a match to load its plays'],['DV Sport PLAY #','']]);
  sh.getRange('A16:B18').setValues([['STEP 3','VolleyReview > Find & Import: import play'],['Status','Ready to search'],['Selected play','']]);
  sh.getRange('A20:B20').merge().setValue('Already-flagged plays keep their original identity. New ones become Saved Plays. Comments are kept in Supabase.');
  sh.getRange('A5:A18').setFontWeight('bold');
  ['B5:B8','B11','B14'].forEach(a=>sh.getRange(a).setBackground('#FFF4DA'));
  sh.getRange('B7:B8').setNumberFormat('yyyy-mm-dd');
  sh.getRange('B5').setDataValidation(SpreadsheetApp.newDataValidation()
    .requireValueInList(['All','BIG TEN','MVC','MAC'],true).setAllowInvalid(true).build());
  sh.setColumnWidth(1,190);sh.setColumnWidth(2,650);
  sh.getRange('B17:B18').setWrap(true);
  return sh;
}

function finderCache_(){
  const book=SpreadsheetApp.getActiveSpreadsheet();
  const sh=ensureSheet_(book,FIND.cache);
  if(!sh.isSheetHidden()){
    book.setActiveSheet(finderSheet_());
    sh.hideSheet();
  }
  return sh;
}
function openFinder(){
  SpreadsheetApp.getActiveSpreadsheet().setActiveSheet(finderSheet_());
}
function finderDate_(cell){
  const sh=finderSheet_(),v=sh.getRange(cell).getValue();
  if(!(v instanceof Date)||isNaN(v.getTime()))throw Error('Enter a valid date in '+cell);
  const tz=SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone();
  return Utilities.formatDate(v,tz,'yyyy-MM-dd');
}
function findDvsportMatches(){
  const sh=finderSheet_(),start=finderDate_('B7'),end=finderDate_('B8');
  if(start>end)throw Error('From date must be before Through date');
  const params=['date_from='+encodeURIComponent(start),'date_to='+encodeURIComponent(end)];
  const conf=String(sh.getRange('B5').getValue()||'').trim();
  const q=String(sh.getRange('B6').getValue()||'').trim();
  if(conf&&conf.toLowerCase()!=='all')params.push('conference='+encodeURIComponent(conf));
  if(q)params.push('q='+encodeURIComponent(q));
  sh.getRange(FIND.status).setValue('Searching DV Sport full-game playlists…');
  try{
    const response=request_('get','/api/v1/dvsport/matches?'+params.join('&'));
    const rows=(response.matches||[]).map(m=>[
      text_(m.match_date+' · '+m.conference+' · '+m.match_name),String(m.match_id)
    ]);
    const cache=finderCache_();
    cache.getRange('A:B').clearContent();
    cache.getRange('A1:B1').setValues([['Match','ID']]);
    if(rows.length){
      cache.getRange(2,1,rows.length,2).setValues(rows);
      sh.getRange(FIND.match).setDataValidation(SpreadsheetApp.newDataValidation()
        .requireValueInRange(cache.getRange(2,1,rows.length,1),true).setAllowInvalid(false).build());
      sh.getRange(FIND.match).setValue(rows[0][0]);
    }else{
      sh.getRange(FIND.match).clearDataValidations().clearContent();
    }
    sh.getRange(FIND.play).clearContent().clearDataValidations();
    sh.getRange('B18').clearContent();
    sh.getRange(FIND.status).setValue(rows.length+' matching matches.'+(response.truncated?' Narrow your search.':''));
    return rows.length;
  }catch(error){
    sh.getRange(FIND.status).setValue('Search failed: '+error.message);
    throw error;
  }
}
function selectedFinderMatch_(){
  const selected=String(finderSheet_().getRange(FIND.match).getValue()||'').trim();
  const sh=finderCache_();
  if(!selected||sh.getLastRow()<2)throw Error('Search matches and select one first');
  const row=sh.getRange(2,1,sh.getLastRow()-1,2).getDisplayValues().find(x=>x[0]===selected);
  if(!row)throw Error('Match not in results; search again');
  return row[1];
}
function loadDvsportPlays(){
  const sh=finderSheet_(),mid=selectedFinderMatch_();
  sh.getRange(FIND.status).setValue('Loading full-game PLAY numbers…');
  try{
    const response=request_('get','/api/v1/dvsport/matches/'+encodeURIComponent(mid)+'/plays');
    const rows=(response.plays||[]).filter(p=>p.play_number!==undefined).map(p=>[
      Number(p.play_number),text_('Set '+(p.set_number||'?')+' · '+(p.score||'—')+' · '+p.angle_count+' cameras')
    ]);
    const cache=finderCache_();
    cache.getRange('D:E').clearContent();
    cache.getRange('D1:E1').setValues([['Play #','Description']]);
    if(rows.length){
      cache.getRange(2,4,rows.length,2).setValues(rows);
      sh.getRange(FIND.play).setDataValidation(SpreadsheetApp.newDataValidation()
        .requireValueInRange(cache.getRange(2,4,rows.length,1),true).setAllowInvalid(false).build());
    }else sh.getRange(FIND.play).clearDataValidations();
    sh.getRange(FIND.play).clearContent();sh.getRange('B18').clearContent();
    sh.getRange(FIND.status).setValue(rows.length+' plays loaded. Choose one in B14.');
    return rows.length;
  }catch(error){sh.getRange(FIND.status).setValue('Failed: '+error.message);throw error;}
}
function showFinderSelection_(){
  const sh=finderSheet_(),number=String(sh.getRange(FIND.play).getValue()||'');
  const cache=finderCache_();
  if(!number||cache.getLastRow()<2)return;
  const row=cache.getRange(2,4,cache.getLastRow()-1,2).getValues().find(r=>String(r[0])===number);
  sh.getRange('B18').setValue(row?'PLAY '+number+' · '+row[1]:'Select a valid PLAY number');
}
function importSelectedPlay(){
  const sh=finderSheet_(),mid=selectedFinderMatch_();
  const number=Number(sh.getRange(FIND.play).getValue());
  if(!Number.isInteger(number)||number<1)throw Error('Select a valid PLAY number in B14');
  const ui=SpreadsheetApp.getUi();
  const answer=ui.alert('Save PLAY '+number+'?','Import DV Sport metadata and all available camera angles. No grade will be added.',ui.ButtonSet.YES_NO);
  if(answer!==ui.Button.YES)return;
  sh.getRange(FIND.status).setValue('Importing play…');
  try{
    const result=request_('post','/api/v1/dvsport/matches/'+encodeURIComponent(mid)+'/plays/'+number+'/import',{});
    sh.getRange(FIND.status).setValue((result.status==='existing'?'Already in library':'Imported')+' · '+result.angle_count+' camera angles · Play ID '+result.play_id);
    syncNow();
    const all=SpreadsheetApp.getActiveSpreadsheet().getSheetByName('All Plays');
    if(all&&all.getLastRow()>4){
      const cell=all.getRange(5,3,all.getLastRow()-4,1).createTextFinder(String(result.play_id)).matchEntireCell(true).findNext();
      if(cell){SpreadsheetApp.getActiveSpreadsheet().setActiveSheet(all);all.setActiveRange(cell);}
    }
    return result;
  }catch(error){sh.getRange(FIND.status).setValue('Import failed: '+error.message);throw error;}
}
function handleFinderEdit(e){
  if(!e||!e.range||e.range.getSheet().getName()!==FIND.name)return;
  if(e.range.getA1Notation()===FIND.match){
    try{loadDvsportPlays();}catch(error){e.range.setNote('Could not load plays: '+error.message);}
  }
  if(e.range.getA1Notation()===FIND.play)showFinderSelection_();
}
