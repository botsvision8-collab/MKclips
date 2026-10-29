const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
async function api(url, options = {}) {
  const r = await fetch(url, options), d = await r.json();
  if (!r.ok || d.ok === false) throw Error(d.error || r.statusText);
  return d;
}
const post = (url, data = {}) => api(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function initSupportAndEasterEgg() {
  const overlay=document.createElement('div');overlay.className='support-overlay';overlay.hidden=true;overlay.innerHTML='<section class="support-card glass" role="dialog" aria-modal="true" aria-labelledby="support-title"><h2 id="support-title"><span>Apóyame mediante una</span> <b>donación</b></h2><p>MKClips es un proyecto independiente. Si te sirve, una donación ayuda a seguir mejorándolo.</p><div class="support-actions"><button class="bt" id="support-ok">Ok</button><button class="bt gh" id="support-cancel">Cancelar</button></div></section>';document.body.appendChild(overlay);
  const closeSupport=()=>{overlay.hidden=true;};
  overlay.addEventListener('pointerdown',e=>{if(e.target===overlay)e.preventDefault();});
  $('#support-cancel').onclick=closeSupport;
  $('#support-ok').onclick=async()=>{closeSupport();try{await post('/app/api/support/open');}catch(e){alert('No se pudo abrir la tip page: '+e.message);}};
  overlay.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();closeSupport();}});
  setTimeout(()=>api('/app/api/support').then(d=>{eggSequence=d.sequence||eggSequence;let launch=new URLSearchParams(location.search).get('launch')||'',anterior='';try{anterior=sessionStorage.getItem('mkclips_support_launch')||'';if(launch)sessionStorage.setItem('mkclips_app_launch',launch);else launch=sessionStorage.getItem('mkclips_app_launch')||d.launch_id||'';if(launch)sessionStorage.setItem('mkclips_support_launch',launch);}catch{}if(d.show&&anterior!==launch){overlay.hidden=false;$('#support-cancel').focus();}}).catch(()=>{}),650);

  const egg=document.createElement('div');egg.className='egg-overlay';egg.hidden=true;egg.innerHTML='<div class="egg-stage"><button class="egg-close" aria-label="Cerrar">×</button><button class="egg-audio" hidden>Activar sonido</button><div class="egg-content"></div></div>';document.body.appendChild(egg);
  const content=egg.querySelector('.egg-content'), audio=egg.querySelector('.egg-audio');let armado=false,timeout=null,ultimo='',pos=0,mediaSize=null,eggSequence=['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','KeyB','KeyA'];try{ultimo=sessionStorage.getItem('mkclips_egg_last')||'';}catch{}
  const apagar=()=>{armado=false;clearTimeout(timeout);document.querySelectorAll('.logo').forEach(x=>x.classList.remove('egg-armed'));};
  const ajustarMedia=(elemento,ancho,alto)=>{if(!ancho||!alto)return;mediaSize={elemento,ancho,alto};const escala=Math.min(1,(window.innerWidth*.82)/ancho,(window.innerHeight*.72)/alto);elemento.style.width=Math.round(ancho*escala)+'px';elemento.style.height=Math.round(alto*escala)+'px';};
  window.addEventListener('resize',()=>{if(mediaSize)ajustarMedia(mediaSize.elemento,mediaSize.ancho,mediaSize.alto);});
  const cerrarEgg=()=>{egg.hidden=true;content.replaceChildren();audio.hidden=true;mediaSize=null;egg.classList.remove('egg-confetti-only');};
  egg.querySelector('.egg-close').onclick=cerrarEgg;egg.addEventListener('click',e=>{if(e.target===egg)cerrarEgg();});audio.onclick=()=>{const v=content.querySelector('video');if(v){v.muted=false;v.play().catch(()=>{});audio.hidden=true;}};
  function confeti(){egg.classList.add('egg-confetti-only');content.innerHTML='<div class="egg-confetti" aria-hidden="true"></div><p>Hecho con cariño por under_mike8</p>';const c=content.querySelector('.egg-confetti');for(let i=0;i<64;i++){const s=document.createElement('i');s.style.left=(Math.random()*100)+'%';s.style.animationDelay=(Math.random()*.7)+'s';s.style.background=i%2?'#4ade80':'#38bdf8';s.style.setProperty('--drift',(Math.random()*120-60)+'px');c.appendChild(s);}}
  function showMedia(file){egg.hidden=false;egg.classList.remove('egg-confetti-only');content.replaceChildren();mediaSize=null;if(!file){confeti();setTimeout(()=>{if(!egg.hidden)cerrarEgg();},2400);return;}const src='/app/easteregg/'+encodeURIComponent(file);if(/\.(mp4|webm)$/i.test(file)){const v=document.createElement('video');v.src=src;v.autoplay=true;v.controls=true;v.playsInline=true;v.onloadedmetadata=()=>ajustarMedia(v,v.videoWidth,v.videoHeight);v.onended=cerrarEgg;v.onerror=()=>{content.replaceChildren();mediaSize=null;confeti();};content.appendChild(v);v.play().catch(()=>{v.muted=true;audio.hidden=false;v.play().catch(()=>{});});}else{const img=document.createElement('img');img.src=src;img.alt='';img.onload=()=>ajustarMedia(img,img.naturalWidth,img.naturalHeight);img.onerror=()=>{content.replaceChildren();mediaSize=null;confeti();};content.appendChild(img);setTimeout(()=>{if(!egg.hidden)cerrarEgg();},5000);}}
  async function disparar(){try{const d=await api('/app/api/easteregg'),files=(d.files||[]);if(!files.length)return showMedia(null);let choices=files;if(files.length>1)choices=files.filter(x=>x!==ultimo);const f=choices[Math.floor(Math.random()*choices.length)];ultimo=f;try{sessionStorage.setItem('mkclips_egg_last',f);}catch{}showMedia(f);}catch{showMedia(null);}}
  function logoClick(e){if(e.target.closest('.logo')){e.preventDefault();if(armado){apagar();return;}armado=true;document.querySelectorAll('.logo').forEach(x=>x.classList.add('egg-armed'));clearTimeout(timeout);timeout=setTimeout(apagar,15000);}}
  document.addEventListener('click',logoClick);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(!egg.hidden){cerrarEgg();return;}if(!overlay.hidden){closeSupport();return;}}if(!armado)return;const t=e.target;if(t.isContentEditable||/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))return;if(e.code===eggSequence[pos]){pos++;if(pos===eggSequence.length){pos=0;apagar();disparar();}}else pos=0;});
}
async function initTheme() {
  try { const d = await api('/app/api/tema'); document.body.classList.toggle('light', d.tema === 'claro'); if ($('#theme')) $('#theme').value = d.tema; $$('[data-logo]').forEach(x => x.src = '/app/static/mkclips_logo_' + (d.tema === 'claro' ? 'claro' : 'oscuro') + '.svg'); } catch {}
}
document.addEventListener('change', async e => {
  if (e.target.id === 'theme') { document.body.classList.toggle('light', e.target.value === 'claro'); $$('[data-logo]').forEach(x => x.src = '/app/static/mkclips_logo_' + e.target.value + '.svg'); await post('/app/api/tema', {tema:e.target.value}); }
});
async function selector(tipo, multiple=false) { const d = await post('/api/seleccionar/' + tipo,{multiple}); return d.cancelado ? [] : (d.rutas||[d.ruta]).filter(Boolean); }
async function pick(btn) {
  try { const values = await selector(btn.dataset.pick,btn.dataset.target==='streams'); if (!values.length) return;
    if (btn.dataset.target === 'streams') await post('/app/api/cola/add', {paths:values});
    else if (btn.dataset.target === 'folder') await post('/app/api/cola/folder', {path:values[0]});
    else $('#dest').value = values[0]; await refreshQueue();
  } catch (e) { alert(e.message); }
}
$$('[data-pick]').forEach(b => b.onclick = () => pick(b));
async function refreshQueue() {
  if (!$('#queue')) return;
  try { const d = await api('/app/api/cola');
    $('#queue').innerHTML = d.queue.map((x,i) => `<div class="tr"><div><input type="radio" name="selected" value="${i}"> ${esc(x.path.split(/[\\/]/).pop())}</div><span>${esc(x.contexto || '—')}</span><div>${esc(x.status)}<div class="bar"><b style="width:${x.status === 'COMPLETADO' ? 100 : x.status === 'PROCESANDO' ? Number(d.progress?.progreso || 0)*100 : 0}%"></b></div></div></div>`).join('');
  } catch (e) { if ($('#msg')) $('#msg').textContent = e.message; }
}
$$('[data-queue]').forEach(b => b.onclick = async () => { try { await post('/app/api/cola/' + b.dataset.queue); await refreshQueue(); } catch(e) { $('#msg').textContent = e.message; } });
if ($('#download')) $('#download').onclick = async () => { try { await post('/api/descargar', {url:$('#url').value, destino:$('#dest').value}); $('#msg').textContent = 'Descarga iniciada.'; } catch(e) { $('#msg').textContent = e.message; } };
if ($('#apply-context')) $('#apply-context').onclick = async () => { try { await post('/app/api/cola/context', {contexto:$('#context').value}); refreshQueue(); } catch(e) { $('#msg').textContent = e.message; } };
if ($('#edit-context')) $('#edit-context').onclick = async () => { try { const i = Number($('input[name=selected]:checked')?.value), d = await api('/app/api/cola'), x = d.queue[i]; if (x) await post('/app/api/cola/item', {path:x.path, contexto:$('#context').value}); refreshQueue(); } catch(e) { $('#msg').textContent = e.message; } };
setInterval(refreshQueue, 1000);
async function refreshHistory() {
  if (!$('#history')) return;
  try { const d = await api('/app/api/historial'), colors = ['#4ade80','#38bdf8','#f1f5f2','#6b7a70','#f59e0b'], total = d.streams.reduce((a,x)=>a+x.clips,0);
    $('#clip-total').innerHTML = `${total}<small>clips</small>`; let at = 0; const cuts = d.streams.map(x => (at += total ? x.clips/total*100 : 0));
    const donut = $('.donut'); if (donut) { donut.style.setProperty('--p1',(cuts[0]||0)+'%'); donut.style.setProperty('--p2',(cuts[1]||cuts[0]||0)+'%'); donut.style.setProperty('--p3',(cuts[2]||cuts[1]||cuts[0]||100)+'%'); }
    $('#history').innerHTML = d.streams.map((x,i)=>`<div class="li"><i style="background:${colors[i%colors.length]}"></i><span class="stream-name">${esc(x.stream)}</span><em>${x.clips}</em></div>`).join('') || '<div class="notice">Sin resultados todavía</div>';
    $('#history-status').textContent = `${d.streams.length} stream(s) · ${d.directory}`;
  } catch(e) { $('#history-status').textContent = e.message; }
}
$('#refresh-history')?.addEventListener('click', refreshHistory);
$('#open-results')?.addEventListener('click', () => post('/app/api/open-results').catch(e=>alert(e.message)));
setInterval(refreshHistory, 5000);
const duration = s => `${Math.floor(Number(s||0)/60)}:${String(Math.floor(Number(s||0)%60)).padStart(2,'0')}`;
function card(c, done=false) { return `<article class="cd glass"><div class="th" style="background-image:url('/app/api/thumb/${encodeURIComponent(c.id)}')"><span class="dur">${duration(c.duration)}</span></div><div class="bd"><div class="tt">${esc(c.title)}</div><div class="mt"><span>${esc(c.stream)}</span><span class="st">${'★'.repeat(c.stars||0)}${'☆'.repeat(5-(c.stars||0))}</span></div><div class="card-actions"><button class="bt gh" data-play="${esc(c.id)}">▶ Reproducir</button><button class="bt" onclick="location.href='/editor/${encodeURIComponent(c.id)}'">Editar</button><button class="bt gh" data-mark="${esc(c.id)}">${done?'Marcar por editar':'Marcar editado'}</button></div></div></article>`; }
async function refreshClips() {
  if (!$('#cards-pending') && !$('#validate-cards')) return;
  try { const d = await api($('#validate-cards') ? '/app/api/validation' : '/app/api/clips'), filter = $('#stream-filter');
    if (filter) { const old=filter.value, streams=[...new Set(d.clips.map(c=>c.stream))]; filter.innerHTML='<option value="">Todos los streams</option>'+streams.map(s=>`<option>${esc(s)}</option>`).join(''); filter.value=old; }
    const clips = filter?.value ? d.clips.filter(c=>c.stream===filter.value) : d.clips, done=clips.filter(c=>c.done), pending=clips.filter(c=>!c.done);
    if ($('#cards-pending')) $('#cards-pending').innerHTML=pending.map(c=>card(c)).join('')||'<div class="notice">No hay clips por editar.</div>';
    if ($('#cards-done')) $('#cards-done').innerHTML=done.map(c=>card(c,true)).join('')||'<div class="notice">Sin clips editados.</div>';
    if ($('#validate-cards')) {
      let validationClips=d.clips;
      const state=$('#validation-state')?.value||'Sin valorar', kind=$('#validation-type')?.value||'Todos', stream=$('#stream-filter')?.value||'';
      if(state==='Sin valorar')validationClips=validationClips.filter(c=>!c.stars&&!c.discarded);
      if(state==='Valorados')validationClips=validationClips.filter(c=>c.stars>0);
      if(state==='Descartados')validationClips=validationClips.filter(c=>c.discarded);
      if(stream)validationClips=validationClips.filter(c=>c.stream===stream);
      if(kind!=='Todos')validationClips=validationClips.filter(c=>kind==='Historias'?c.type==='Historia':c.type!=='Historia');
      if($('#validate-sort')?.value==='stream')validationClips.sort((a,b)=>a.stream.localeCompare(b.stream));
      $('#validate-cards').innerHTML=validationClips.length?validationClips.map(c=>`<article class="cd glass"><div class="th" style="background-image:url('/app/api/thumb/${encodeURIComponent(c.id)}')"><span class="dur">${duration(c.duration)}</span></div><div class="bd"><div class="tt">${esc(c.title)}</div><div class="mt">${esc(c.stream)} · ${esc(c.type)} <span class="st">${'\u2605'.repeat(c.stars||0)}${'\u2606'.repeat(5-(c.stars||0))}</span></div><div class="card-actions"><button class="bt gh" data-play="${esc(c.id)}">▶ Reproducir</button></div><label>Valoración <select class="field rating" data-id="${esc(c.id)}"><option value="">Sin cambios</option>${[1,2,3,4,5].map(i=>`<option value="${i}">${i} estrellas</option>`).join('')}<option value="0">Descartar</option></select></label></div><label class="setting">Motivo<select class="field reason" data-for="${esc(c.id)}"><option value="">Opcional</option><option value="humor">Me hizo re\u00edr</option><option value="climax">Remate o clímax fuerte</option><option value="habilidad">Jugada destacada</option><option value="historia">Historia fácil de seguir</option><option value="reaccion">Reacción o emoci\u00f3n</option><option value="sorpresa">Sorpresa</option><option value="aburrido">Aburrido</option><option value="contexto">Falta contexto</option><option value="repetitivo">Repetitivo</option><option value="corte">Mal cortado</option><option value="tecnico">Problema técnico</option></select></label><textarea class="field comment" data-for="${esc(c.id)}" placeholder="Comentario opcional"></textarea></div></article>`).join(''):'<div class="notice">No hay clips con este filtro.</div>';
    }
    $$('[data-play]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const d=await post('/app/api/clips/play',{id:b.dataset.play});const msg=$('#validate-msg');if(msg)msg.textContent=d.mensaje||'Abriendo reproductor.';else{b.title='Clip abierto en el reproductor del sistema';setTimeout(()=>{if(b.isConnected)b.title='';},2500);}}catch(e){const msg=$('#validate-msg');if(msg)msg.textContent=e.message;else{b.title=e.message;alert(e.message);}}finally{b.disabled=false;}});
    $$('[data-mark]').forEach(b=>b.onclick=async()=>{await post('/app/api/clips/mark',{id:b.dataset.mark,done:!b.textContent.includes('por editar')});refreshClips();});
  } catch(e) { console.warn(e); }
}
$('#stream-filter')?.addEventListener('change',refreshClips); $('#validation-state')?.addEventListener('change',refreshClips); $('#validation-type')?.addEventListener('change',refreshClips); $('#validate-sort')?.addEventListener('change',refreshClips); $('#refresh-clips')?.addEventListener('click',refreshClips); $('#refresh-validation')?.addEventListener('click',refreshClips);
$$('[data-vista]').forEach(b=>b.onclick=()=>{$$('[data-vista]').forEach(x=>x.classList.toggle('on',x===b));$('#vista-por').hidden=b.dataset.vista!=='por';$('#vista-ed').hidden=b.dataset.vista!=='ed';});
$('#save-ratings')?.addEventListener('click',async()=>{const changes=$$('.rating').filter(x=>x.value!=='').map(x=>({id:x.dataset.id,rating:Number(x.value),discarded:x.value==='0',motivo:$(`.reason[data-for="${x.dataset.id}"]`)?.value||'',comentario:$(`.comment[data-for="${x.dataset.id}"]`)?.value||''}));if(changes.some(x=>x.discarded)&&!confirm('Los clips descartados se eliminarán del disco. ¿Continuar?'))return;try{await post('/app/api/clips/ratings',{changes});$('#validate-msg').textContent='Valoraciones guardadas.';refreshClips();}catch(e){$('#validate-msg').textContent=e.message;}});
if ($('#dest')) api('/app/api/config').then(c=>$('#dest').value=c.CARPETA_STREAMS||'').catch(()=>{});
initTheme(); initSupportAndEasterEgg(); refreshClips(); refreshHistory(); refreshQueue();

$('#trim-clips')?.addEventListener('click',async()=>{if(!confirm('Se recortar? el final de los clips que superen la duración m?xima. ¿Continuar?'))return;try{const d=await post('/app/api/clips/trim');$('#validate-msg').textContent=`Recortados: ${d.recortados}${d.errores.length?' ? fallidos: '+d.errores.length:''}`;refreshClips()}catch(e){$('#validate-msg').textContent=e.message}});

/* MKCLIPS_FEEDBACK_COMPAT */
/* feedback.js — respuesta visible al presionar botones, sin tocar el código de cada pantalla.
   Cargar al final de <body> en todas las pantallas. */
(function () {
  "use strict";
  var ultimo = null, ultimoT = 0;

  // 1) Al presionar cualquier botón se oscurece un instante (clase .pulsado).
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("button, .bt");
    if (!b || b.disabled) return;
    ultimo = b; ultimoT = Date.now();
    b.classList.add("pulsado");
    setTimeout(function () { b.classList.remove("pulsado"); }, 320);
  }, true);

  // 2) Si el clic dispara una petición al servidor (Refrescar, Actualizar, Guardar, Probar…),
  //    el botón queda "ocupado" (atenuado con círculo girando) hasta que la petición termina.
  var fetchOriginal = window.fetch;
  if (fetchOriginal) {
    window.fetch = function () {
      var btn = (ultimo && Date.now() - ultimoT < 400) ? ultimo : null;
      var p = fetchOriginal.apply(this, arguments);
      if (btn) {
        btn._pend = (btn._pend || 0) + 1;
        btn.classList.add("is-busy");
        var fin = function (ok) {
          btn._pend = Math.max(0, (btn._pend || 1) - 1);
          if (!btn._pend) {
            btn.classList.remove("is-busy");
            if (ok) { btn.classList.add("is-ok"); setTimeout(function () { btn.classList.remove("is-ok"); }, 900); }
          }
        };
        p.then(function (r) { fin(r && r.ok !== false); }, function () { fin(false); });
      }
      return p;
    };
  }

  // 3) API opcional para operaciones sin fetch: mkBusy(boton, promesa)
  window.mkBusy = function (btn, promesa) {
    btn.classList.add("is-busy");
    return Promise.resolve(promesa).finally(function () { btn.classList.remove("is-busy"); });
  };
})();
