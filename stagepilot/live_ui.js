const token = document.querySelector('meta[name="stagepilot-token"]').content;
const $ = id => document.getElementById(id);
const headers = {'Content-Type':'application/json', 'X-StagePilot-Token': token};
const profileKey = 'stagepilot.cameraProfiles';
let displayed = -1, polling = false, currentFrame = null;
let profiles = [], profile = null, activeControl = null, ptzQueue = Promise.resolve();

async function post(path, data) {
  const response = await fetch(path, {method:'POST', headers, body:JSON.stringify(data)});
  if (!response.ok) {
    let result = {};
    try { result = await response.json(); } catch {}
    throw new Error(result.error || 'Request failed');
  }
}

function isPrivateIPv4(host) {
  const parts = host.split('.');
  if (parts.length !== 4 || parts.some(part => !/^\d{1,3}$/.test(part) ||
      Number(part) > 255 || (part.length > 1 && part[0] === '0'))) return false;
  const [a, b] = parts.map(Number);
  return a === 10 || (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) || (a === 169 && b === 254);
}

function profileFromForm() {
  const name = $('profile-name').value.trim();
  const url = $('url').value.trim();
  const host = $('ptz-host').value.trim();
  const port = Number($('ptz-port').value);
  let parsedUrl;
  try { parsedUrl = new URL(url); } catch { return null; }
  if (!name || name.length > 60 || !['rtsp:', 'rtsps:'].includes(parsedUrl.protocol) ||
      !parsedUrl.hostname || !isPrivateIPv4(host) || !Number.isInteger(port) ||
      port < 1 || port > 65535) return null;
  return {id:profile && profile.name.toLowerCase() === name.toLowerCase()
      ? profile.id : crypto.randomUUID(), name, url, host, port};
}

function updatePtzEnabled() {
  const matches = profile && profile.host === $('ptz-host').value.trim() &&
    profile.port === Number($('ptz-port').value);
  if (!matches && activeControl) {
    stopActiveControl();
    sendPtz('stop_all');
  }
  document.querySelectorAll('[data-ptz]').forEach(button => { button.disabled = !matches; });
  $('profile-delete').disabled = !profile;
  $('profile-edit').disabled = !profile;
  $('ptz-save').textContent = profile ? 'Update profile & reconnect' : 'Save profile & connect';
}

function showProfileForm(show) {
  $('profile-panel').hidden = !show;
}

function renderProfiles(selectedId = '') {
  const select = $('profile-select');
  select.replaceChildren(new Option('Select camera profile', ''));
  profiles.forEach(item => select.add(new Option(item.name, item.id)));
  select.value = selectedId;
  $('profile-edit').disabled = !selectedId;
  $('profile-delete').disabled = !selectedId;
}

function isProfile(value) {
  return value && typeof value.id === 'string' && typeof value.name === 'string' &&
    value.name.trim() && value.name.length <= 60 && typeof value.url === 'string' &&
    value.url.length <= 2048 && (() => {
      try {
        const url = new URL(value.url);
        return ['rtsp:', 'rtsps:'].includes(url.protocol) && !!url.hostname;
      } catch { return false; }
    })() && typeof value.host === 'string' && isPrivateIPv4(value.host) &&
    Number.isInteger(value.port) &&
    value.port >= 1 && value.port <= 65535;
}

function loadProfiles() {
  try {
    const saved = localStorage.getItem(profileKey);
    if (saved) {
      const values = JSON.parse(saved);
      if (!Array.isArray(values)) throw new Error('Invalid profile list');
      profiles = values.filter(isProfile).slice(0, 20);
      if (profiles.length !== values.length) {
        localStorage.setItem(profileKey, JSON.stringify(profiles));
        $('profile-message').textContent = 'Invalid saved profiles were discarded.';
      }
    }
    renderProfiles();
  } catch {
    profiles = [];
    renderProfiles();
    $('profile-message').textContent = 'Could not load saved profiles from this browser.';
  }
}

function sendPtz(action, direction, speed, target = profile) {
  if (!target) return Promise.resolve();
  const data = {host:target.host, port:target.port, action};
  if (direction) data.direction = direction;
  if (speed !== undefined) data.speed = speed;
  ptzQueue = ptzQueue.then(async () => {
    await post('/ptz', data);
    $('ptz-status').textContent = 'PTZ command sent via UDP; the camera does not confirm movement.';
  }).catch(error => {
    $('ptz-status').textContent = `PTZ command failed: ${error.message}`;
  });
  return ptzQueue;
}

function stopActiveControl() {
  if (!activeControl) return;
  const target = activeControl.target;
  activeControl = null;
  sendPtz('stop_all', undefined, undefined, target);
}

$('ptz-save').onclick = async () => {
  const next = profileFromForm();
  if (!next) {
    $('profile-message').textContent = 'Enter a profile name, valid RTSP URL, private IPv4 camera address, and UDP port from 1 to 65535.';
    return;
  }
  if (profile) {
    stopActiveControl();
    await sendPtz('stop_all');
  }
  try {
    const index = profiles.findIndex(item => item.id === next.id ||
      item.name.toLowerCase() === next.name.toLowerCase());
    if (index >= 0) profiles[index] = next;
    else if (profiles.length < 20) profiles.push(next);
    else {
      $('profile-message').textContent = 'Profile limit reached. Delete a profile before saving another.';
      return;
    }
    localStorage.setItem(profileKey, JSON.stringify(profiles));
    profile = null;
    $('profile-name').value = next.name;
    $('url').value = next.url;
    $('ptz-host').value = next.host;
    $('ptz-port').value = next.port;
    renderProfiles(next.id);
    updatePtzEnabled();
    $('profile-select').dispatchEvent(new Event('change'));
  } catch {
    $('profile-message').textContent = 'Could not save the profile in this browser.';
  }
};

['ptz-host','ptz-port'].forEach(id => $(id).addEventListener('input', updatePtzEnabled));
loadProfiles();

$('profile-select').onchange = async () => {
  const selected = profiles.find(item => item.id === $('profile-select').value);
  if (!selected) {
    if (profile) {
      stopActiveControl();
      await sendPtz('stop_all');
    }
    profile = null;
    updatePtzEnabled();
    showProfileForm(true);
    $('ptz-status').textContent = 'Select a camera profile to enable PTZ.';
    return;
  }
  if (profile) {
    stopActiveControl();
    await sendPtz('stop_all');
  }
  profile = selected;
  $('profile-name').value = selected.name;
  $('url').value = selected.url;
  $('ptz-host').value = selected.host;
  $('ptz-port').value = selected.port;
  updatePtzEnabled();
  showProfileForm(false);
  $('ptz-status').textContent = `PTZ ready for ${selected.name}.`;
  $('status').textContent = `Connecting to ${selected.name}…`;
  try { await startPreview(selected.url, true); }
  catch (error) { $('status').textContent = `Profile loaded, but stream connection failed: ${error.message}`; }
};

$('profile-delete').onclick = async () => {
  if (!profile || !confirm(`Delete the "${profile.name}" profile?`)) return;
  stopActiveControl();
  await sendPtz('stop_all');
  let stopWarning = '';
  try {
    const status = await previewStatus();
    if (['connecting','running','stopping'].includes(status.status)) await post('/stop',{});
  } catch {
    stopWarning = ' The preview could not be stopped.';
  }
  profiles = profiles.filter(item => item.id !== profile.id);
  try {
    localStorage.setItem(profileKey, JSON.stringify(profiles));
    profile = null;
    $('profile-name').value = '';
    $('url').value = '';
    $('ptz-host').value = '';
    $('ptz-port').value = '52381';
    renderProfiles();
    updatePtzEnabled();
    showProfileForm(true);
    $('profile-message').textContent = `Profile deleted.${stopWarning}`;
  } catch {
    $('profile-message').textContent = 'Could not update saved profiles in this browser.';
  }
};

$('profile-edit').onclick = () => {
  showProfileForm(true);
  $('profile-name').focus();
};

const panTiltSpeed = $('ptz-speed');
const zoomSpeed = $('zoom-speed');
panTiltSpeed.oninput = () => { $('ptz-speed-value').textContent = panTiltSpeed.value; };
zoomSpeed.oninput = () => { $('zoom-speed-value').textContent = zoomSpeed.value; };

document.querySelectorAll('[data-ptz]').forEach(button => {
  const kind = button.dataset.ptz;
  const direction = button.dataset.direction;
  button.addEventListener('pointerdown', event => {
    if (button.disabled || kind === 'stop_all') return;
    event.preventDefault();
    if (activeControl) stopActiveControl();
    activeControl = {
      kind,
      button,
      pointerId:event.pointerId,
      target:{host:profile.host, port:profile.port},
    };
    const speed = kind === 'pan_tilt' ? Number(panTiltSpeed.value) : Number(zoomSpeed.value);
    sendPtz(kind, direction, speed);
    button.setPointerCapture(event.pointerId);
  });
  button.addEventListener('click', event => {
    if (kind === 'stop_all') {
      stopActiveControl();
      sendPtz('stop_all');
    } else if (event.detail === 0 && !button.disabled) {
      const speed = kind === 'pan_tilt' ? Number(panTiltSpeed.value) : Number(zoomSpeed.value);
      sendPtz(kind, direction, speed).then(() => sendPtz(kind, 'stop'));
    }
  });
});

function releasePointerControl(event) {
  if (activeControl && activeControl.pointerId === event.pointerId) stopActiveControl();
}
window.addEventListener('pointerup', releasePointerControl);
window.addEventListener('pointercancel', releasePointerControl);
document.querySelectorAll('[data-ptz]').forEach(button => {
  button.addEventListener('lostpointercapture', event => {
    if (activeControl && activeControl.pointerId === event.pointerId) stopActiveControl();
  });
});
window.addEventListener('blur', () => {
  stopActiveControl();
  if (profile) sendPtz('stop_all');
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden && profile) {
    stopActiveControl();
    sendPtz('stop_all');
  }
});

$('show').onclick = () => {
  const input=$('url');
  input.type=input.type==='password'?'text':'password';
  $('show').textContent=input.type==='password'?'Show':'Hide';
};
$('fps').oninput = () => {
  $('fps-value').textContent=$('fps').value;
  post('/fps',{fps:Number($('fps').value)}).catch(()=>{});
};
$('confidence').oninput = () => {
  $('confidence-value').textContent=Number($('confidence').value).toFixed(2);
  post('/confidence',{confidence:Number($('confidence').value)}).catch(()=>{});
};

async function previewStatus() {
  const response = await fetch('/status',{headers:{'X-StagePilot-Token':token},cache:'no-store'});
  if (!response.ok) throw new Error('Preview server unavailable');
  return response.json();
}

async function startPreview(url, switchProfile = false) {
  $('connect').disabled = true;
  try {
    if (switchProfile) {
      const current = await previewStatus();
      if (['connecting','running','stopping'].includes(current.status)) {
        await post('/stop',{});
        let stopped = false;
        for (let attempt = 0; attempt < 30; attempt++) {
          await new Promise(resolve => setTimeout(resolve, 300));
          const status = await previewStatus();
          if (!['connecting','running','stopping'].includes(status.status)) {
            stopped = true;
            break;
          }
        }
        if (!stopped) throw new Error('The previous stream did not stop in time.');
      }
    }
    let started = false;
    for (let attempt = 0; attempt < (switchProfile ? 10 : 1); attempt++) {
      try {
        await post('/start',{url,fps:Number($('fps').value),backend:$('backend').value});
        started = true;
        break;
      } catch (error) {
        if (!switchProfile || !error.message.includes('Stop the existing preview first.')) throw error;
        await new Promise(resolve => setTimeout(resolve, 200));
      }
    }
    if (!started) throw new Error('The previous stream is still stopping.');
    displayed = -1;
    await refresh();
  } catch (error) {
    $('connect').disabled = false;
    throw error;
  }
}

$('connect').onclick = async () => {
  try { await startPreview($('url').value); }
  catch (error) { $('status').textContent=error.message; }
};
$('stop').onclick = async () => {
  $('stop').disabled=true;
  try { await post('/stop',{}); await refresh(); }
  catch (e) { $('status').textContent=e.message; }
};

async function refresh() {
  if (polling) return;
  polling=true;
  try {
    const response=await fetch('/status',{headers:{'X-StagePilot-Token':token},cache:'no-store'});
    if(!response.ok) throw new Error('Preview unavailable');
    const s=await response.json(), active=['connecting','running','stopping'].includes(s.status);
    $('status').textContent=s.message;
    $('status-dot').className='dot '+s.status;
    $('connect').disabled=active;
    $('stop').disabled=!active || s.status==='stopping';
    $('live-tag').textContent=s.status==='running'?'LIVE':'OFFLINE';
    $('device-label').textContent=s.backend==='directml'?'DIRECTML':'CPU';
    $('backend').disabled=active;
    $('actual').textContent=s.actual_fps ? s.actual_fps+' fps':'—';
    $('inference').textContent=s.inference_ms ? s.inference_ms+' ms':'—';
    $('people').textContent=s.frame_id ? s.people:'—';
    if(s.status!=='running') {
      $('preview').hidden=true;
      $('empty').hidden=false;
    } else if(s.frame_id && s.frame_id!==displayed) {
      const image=await fetch('/frame',{headers:{'X-StagePilot-Token':token},cache:'no-store'});
      if(image.ok) {
        const old=currentFrame;
        currentFrame=URL.createObjectURL(await image.blob());
        $('preview').src=currentFrame;
        $('preview').hidden=false;
        $('empty').hidden=true;
        displayed=s.frame_id;
        if(old) URL.revokeObjectURL(old);
      }
    }
  } catch(e) { $('status').textContent='Preview server unavailable'; }
  finally { polling=false; }
}

refresh();
setInterval(refresh,500);
