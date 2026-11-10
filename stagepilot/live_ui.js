const token = document.querySelector('meta[name="stagepilot-token"]').content;
const $ = id => document.getElementById(id);
const headers = {'Content-Type':'application/json', 'X-StagePilot-Token': token};
let displayed = -1, polling = false, currentFrame = null;
async function post(path, data) {
  const response = await fetch(path, {method:'POST', headers, body:JSON.stringify(data)});
  if (!response.ok) { const result = await response.json(); throw new Error(result.error || 'Request failed'); }
}
$('show').onclick = () => { const input=$('url'); input.type=input.type==='password'?'text':'password'; $('show').textContent=input.type==='password'?'Show':'Hide'; };
$('fps').oninput = () => { $('fps-value').textContent=$('fps').value; post('/fps',{fps:Number($('fps').value)}).catch(()=>{}); };
$('confidence').oninput = () => { $('confidence-value').textContent=Number($('confidence').value).toFixed(2); post('/confidence',{confidence:Number($('confidence').value)}).catch(()=>{}); };
$('connect').onclick = async () => {
  $('connect').disabled=true;
  try { await post('/start',{url:$('url').value,fps:Number($('fps').value),backend:$('backend').value}); $('url').value=''; displayed=-1; await refresh(); }
  catch (e) { $('status').textContent=e.message; $('connect').disabled=false; }
};
$('stop').onclick = async () => { $('stop').disabled=true; try { await post('/stop',{}); await refresh(); } catch (e) { $('status').textContent=e.message; } };
async function refresh() {
  if (polling) return;
  polling=true;
  try {
    const response=await fetch('/status',{headers:{'X-StagePilot-Token':token},cache:'no-store'});
    if(!response.ok) throw new Error('Preview unavailable');
    const s=await response.json(), active=['connecting','running','stopping'].includes(s.status);
    $('status').textContent=s.message; $('status-dot').className='dot '+s.status;
    $('connect').disabled=active; $('stop').disabled=!active || s.status==='stopping';
    $('live-tag').textContent=s.status==='running'?'LIVE':'OFFLINE';
    $('device-label').textContent=s.backend==='directml'?'DIRECTML':'CPU';
    $('backend').disabled=active;
    $('actual').textContent=s.actual_fps ? s.actual_fps+' fps':'—';
    $('inference').textContent=s.inference_ms ? s.inference_ms+' ms':'—';
    $('people').textContent=s.frame_id ? s.people:'—';
    if(s.status!=='running') { $('preview').hidden=true; $('empty').hidden=false; }
    else if(s.frame_id && s.frame_id!==displayed) {
      const image=await fetch('/frame',{headers:{'X-StagePilot-Token':token},cache:'no-store'});
      if(image.ok) { const old=currentFrame; currentFrame=URL.createObjectURL(await image.blob()); $('preview').src=currentFrame; $('preview').hidden=false; $('empty').hidden=true; displayed=s.frame_id; if(old) URL.revokeObjectURL(old); }
    }
  } catch(e) { $('status').textContent='Preview server unavailable'; }
  finally { polling=false; }
}
refresh(); setInterval(refresh,500);
