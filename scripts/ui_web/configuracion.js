(() => {
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const api = async (url, data) => {
    const r = await fetch(url, data ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)} : {});
    const d = await r.json();
    if (!r.ok || d.ok === false) throw Object.assign(Error(d.error || r.statusText), {errors:d.errors || {}});
    return d;
  };
  let cfg = {}, engine = 'whisper_local';
  const labels = {
    CARPETA_STREAMS:'Streams grabados', CARPETA_CLIPS_BASE:'Clips generados', CARPETA_EDITADOS:'Clips editados', CARPETA_RESULTADOS:'Carpeta de resultados',
    OBS_WS_HOST:'Host', OBS_WS_PUERTO:'Puerto', OBS_WS_CONTRASENA:'Contraseña',
    NUM_PROCESOS_TRANSCRIPCION:'Procesos en paralelo', USAR_GPU_TRANSCRIPCION:'Usar GPU',
    ASSEMBLYAI_API_KEY_ENV:'Variable de la clave', ASSEMBLYAI_MODELOS:'Modelos', ASSEMBLYAI_TERMINOS:'Términos del juego',
    ASSEMBLYAI_PAUSA_SEG:'Pausa entre segmentos', ASSEMBLYAI_MAX_SEGMENTO_SEG:'Segmento máximo', ASSEMBLYAI_ESPERA_MAX_MIN:'Espera máxima',
    LLM_PROVEEDOR:'Proveedor', LLM_MODELO:'Modelo', LLM_BASE_URL:'URL base', LLM_API_KEY_ENV:'Variable de la clave',
    OLLAMA_MODO:'Modo', OLLAMA_HOST:'Servidor', OLLAMA_MODELO:'Modelo', CONTEXTO_PROYECTO:'Sobre tu canal y tu contenido',
    DURACION_MIN_CLIP:'Mínima', DURACION_MAX_CLIP:'Máxima'
  };
  const types = {
    OBS_WS_PUERTO:'number', NUM_PROCESOS_TRANSCRIPCION:'number', ASSEMBLYAI_PAUSA_SEG:'number', ASSEMBLYAI_MAX_SEGMENTO_SEG:'number',
    ASSEMBLYAI_ESPERA_MAX_MIN:'number', DURACION_MIN_CLIP:'number', DURACION_MAX_CLIP:'number'
  };
  const units = {ASSEMBLYAI_PAUSA_SEG:'seg',ASSEMBLYAI_MAX_SEGMENTO_SEG:'seg',ASSEMBLYAI_ESPERA_MAX_MIN:'min',DURACION_MIN_CLIP:'seg',DURACION_MAX_CLIP:'seg'};
  const hiddenSecret = k => k === 'OBS_WS_CONTRASENA';
  function control(k, extra='') {
    const type = hiddenSecret(k) ? 'password' : (types[k] || 'text');
    let value = cfg[k] ?? '';
    if (Array.isArray(value)) value = value.join(', ');
    if (hiddenSecret(k)) value = '';
    const placeholder = hiddenSecret(k) ? 'Dejar en blanco para conservar' : (k === 'CARPETA_RESULTADOS' ? 'Predeterminada' : '');
    const input = `<input class="in ${extra}" id="cfg-${k}" data-config="${k}" type="${type}" value="${esc(value)}" placeholder="${placeholder}" autocomplete="${type==='password'?'new-password':'off'}">`;
    return units[k] ? `<div class="un">${input}<span>${units[k]}</span></div>` : input;
  }
  function field(k, opts={}) {
    const title = opts.title || labels[k] || k;
    const input = k === 'OBS_MODO_GRABACION_DEFAULT'
      ? `<select class="in" id="cfg-${k}" data-config="${k}">${[['horizontal','Horizontal'],['vertical','Vertical'],['ambos','Ambos']].map(([v,t])=>`<option value="${v}" ${cfg[k]===v?'selected':''}>${t}</option>`).join('')}</select>`
      : control(k);
    const browse = opts.browse ? `<button class="bt gh" type="button" data-browse="${k}">Examinar</button>` : '';
    const row = opts.row || browse ? `<div class="pr">${input}${browse}</div>` : input;
    return `<div class="f" data-setting="${k}"><label for="cfg-${k}">${title}</label>${row}${opts.help?`<small class="help">${opts.help}</small>`:''}</div>`;
  }
  function toggle(k, title, desc) {
    const on = !!cfg[k];
    return `<div class="tr"><div>${title}<span>${desc}</span></div><button type="button" class="sw ${on?'':'off'}" role="switch" aria-checked="${on}" aria-label="${esc(title)}" data-switch="${k}"></button></div>`;
  }
  const navGroups = [
    ['obs','OBS','<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>',[['obs-connection','Conexión'],['obs-panel','Panel dentro de OBS']]],
    ['transcripcion','Transcripción','<path d="M12 3v12M8 7v4M16 7v4M4 10v2M20 10v2M9 21h6M12 17v4"/>',[['trans-motor','Motor'],['trans-rendimiento','Rendimiento'],['trans-assembly','AssemblyAI'],['trans-cortes','Cortes'],['trans-espera','Espera']]],
    ['ia','IA','<path d="M12 3l2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2z"/>',[['ia-modelo','Modelo'],['ia-clave','Clave de acceso'],['ia-ollama','Ollama']]],
    ['contexto','Contexto para la IA','<path d="M5 4h14v16H5zM9 9h6M9 13h6"/>',[['ctx-about','Sobre tu canal'],['ctx-criteria','Criterios del creador']]],
    ['mantenimiento','Mantenimiento','<path d="M14 6l4 4-9 9H5v-4zM13 7l4 4"/>',[['maint-results','Resultados'],['maint-temp','Archivos temporales']]]
  ];
  function general() {
    const pane=$('#v-gen');
    pane.querySelectorAll('[data-config]').forEach(x=>{if(cfg[x.dataset.config]!==undefined)x.value=cfg[x.dataset.config]});
    const modeControl=$('#cfg-OBS_MODO_GRABACION_DEFAULT'); if(modeControl)modeControl.value=cfg.OBS_MODO_GRABACION_DEFAULT||'horizontal';
    $$('[data-switch]').forEach(x=>{if(cfg[x.dataset.switch]!==undefined){const on=!!cfg[x.dataset.switch];x.setAttribute('aria-checked',String(on));x.classList.toggle('off',!on);}});
    browseHandlers();
  }
  function extraPanel() {
    const script = cfg.obs_script || '';
    return `<div class="f"><label>Enlace del panel</label><div class="pr"><input class="in" readonly value="http://localhost:5678"><button class="bt gh" type="button" data-copy="http://localhost:5678">Copiar</button></div></div>
      <div class="f"><label>Script de OBS</label><div class="pr"><input class="in" readonly value="${esc(script)}"><button class="bt gh" type="button" data-copy="${esc(script)}">Copiar</button></div></div>
      <div class="pr"><button class="bt gh sm" type="button" id="panel-start">Iniciar el panel</button><button class="bt gh sm" type="button" id="panel-check">Comprobar si está activo</button></div><div id="panel-status" class="notice"></div>`;
  }
  function tile(title, desc, content, id='') {
    return `<div class="tile" ${id?`id="${id}"`:''}><div class="tt">${title}<span>${desc}</span></div>${content}</div>`;
  }
  function advanced() {
    $('#advanced-nav').innerHTML = navGroups.map(([id,name,icon,items])=>`<div class="h"><svg viewBox="0 0 24 24">${icon}</svg>${name}</div>${items.map(([target,label])=>`<a href="#${target}" data-jump="${target}">${label}</a>`).join('')}`).join('');
    const obs = `<section class="cat glass" id="cat-obs"><div class="cth"><div class="ci"><svg viewBox="0 0 24 24">${navGroups[0][2]}</svg></div><div><div class="cn">Conexión con <b>OBS</b></div><div class="cd">Cómo habla MKClips con OBS. Solo si cambiaste algo en OBS.</div></div></div>
      <div class="fn c2"><div class="tile" id="obs-connection"><div class="tt">Conexión<span>Datos del WebSocket de OBS</span></div>${field('OBS_WS_HOST')}${field('OBS_WS_PUERTO')}${field('OBS_WS_CONTRASENA')}</div>
      <div class="tile" id="obs-panel"><div class="tt">Panel dentro de OBS<span>Para grabar y procesar sin salir de OBS</span></div>${extraPanel()}</div></div></section>`;
    const transcription = `<section class="cat glass" id="cat-transcripcion"><div class="cth"><div class="ci"><svg viewBox="0 0 24 24">${navGroups[1][2]}</svg></div><div><div class="cn">Trans<b>cripción</b></div><div class="cd">Cómo se convierte el audio del stream en texto.</div></div></div>
      <div class="fn c3">${tile('Motor','Elige quién transcribe',`<div class="seg2"><button type="button" data-engine="whisper_local">Whisper local</button><button type="button" data-engine="assemblyai">AssemblyAI</button></div>`,'trans-motor')}
      ${tile('Rendimiento (Whisper)','Velocidad según tu equipo',`${field('NUM_PROCESOS_TRANSCRIPCION')}${toggle('USAR_GPU_TRANSCRIPCION','Usar GPU','Si tu equipo tiene tarjeta compatible')}<div class="info">${cfg.cpu_logicos} CPU · recomendado ${cfg.cpu_limite_recomendado}</div>`,'trans-rendimiento')}
      ${tile('AssemblyAI','Solo si usas este motor',`${field('ASSEMBLYAI_API_KEY_ENV')}${field('ASSEMBLYAI_MODELOS')}${field('ASSEMBLYAI_TERMINOS')}<div class="f"><label for="assembly-key">Clave (solo esta sesión)</label><input class="in" id="assembly-key" type="password" autocomplete="new-password"></div>`,'trans-assembly')}</div>
      <div class="fn c3">${tile('Cortes','Cómo se parte el texto',`${field('ASSEMBLYAI_PAUSA_SEG')}${field('ASSEMBLYAI_MAX_SEGMENTO_SEG')}`,'trans-cortes')}${tile('Espera','Cuánto aguardar el resultado',field('ASSEMBLYAI_ESPERA_MAX_MIN'),'trans-espera')}<div></div></div></section>`;
    const ai = `<section class="cat glass" id="cat-ia"><div class="cth"><div class="ci"><svg viewBox="0 0 24 24">${navGroups[2][2]}</svg></div><div><div class="cn">IA que <b>elige los clips</b></div><div class="cd">El modelo que decide qué momentos valen la pena.</div></div></div>
      <div class="fn c2">${tile('Modelo','Quién analiza el stream',`${field('LLM_PROVEEDOR')}${field('LLM_MODELO')}${field('LLM_BASE_URL')}`,'ia-modelo')}
      ${tile('Clave de acceso','Tu clave nunca se guarda en el archivo',`${field('LLM_API_KEY_ENV')}<div class="f"><label for="llm-key">Clave (solo esta sesión)</label><input class="in" id="llm-key" type="password" placeholder="Pega tu clave" autocomplete="new-password"></div>`,'ia-clave')}
      ${tile('Ollama','Solo si la IA corre en Ollama',`${field('OLLAMA_MODO')}${field('OLLAMA_HOST')}${field('OLLAMA_MODELO')}`,'ia-ollama')}<div></div></div></section>`;
    const context = `<section class="cat glass" id="cat-contexto"><div class="cth"><div class="ci"><svg viewBox="0 0 24 24">${navGroups[3][2]}</svg></div><div><div class="cn">Contexto <b>para la IA</b></div><div class="cd">Cuanto mejor la describas, mejores clips elige.</div></div></div>
      <div class="fn c2">${tile('Sobre tu canal','Qué juegas y qué público tienes',`<div class="f"><label for="cfg-CONTEXTO_PROYECTO">Sobre tu canal y tu contenido</label><textarea class="ta" id="cfg-CONTEXTO_PROYECTO" data-config="CONTEXTO_PROYECTO" placeholder="Qué juegas, qué tipo de público tienes…">${esc(cfg.CONTEXTO_PROYECTO||'')}</textarea></div>`,'ctx-about')}
      ${tile('Criterios del creador','Qué te gusta que se elija',`<textarea class="ta" id="criteria"></textarea><div class="pr" style="justify-content:flex-end"><button class="bt gh" type="button" id="update-criteria">Actualizar con IA</button><button class="bt gh" type="button" id="save-criteria">Guardar criterios</button></div>`,'ctx-criteria')}</div></section>`;
    const maintenance = `<section class="cat glass" id="cat-mantenimiento"><div class="cth"><div class="ci"><svg viewBox="0 0 24 24">${navGroups[4][2]}</svg></div><div><div class="cn">Manten<b>imiento</b></div><div class="cd">Resultados guardados y limpieza de archivos temporales.</div></div></div>
      <div class="fn c2">${tile('Resultados','Dónde quedan los análisis',field('CARPETA_RESULTADOS',{browse:true}),'maint-results')}${tile('Archivos temporales','Libera espacio sin tocar tus clips',`<div class="pr"><button class="bt gh" type="button" id="clean-temp">Limpiar temporales</button></div>`,'maint-temp')}</div></section>`;
    $('#advanced-content').innerHTML = obs + transcription + ai + context + maintenance;
    $$('[data-engine]').forEach(b=>b.classList.toggle('on',b.dataset.engine===engine));
    function syncEngine() {
      const assembly = engine === 'assemblyai';
      $('#trans-rendimiento').hidden = assembly;
      $('#trans-assembly').hidden = !assembly;
      $('#trans-cortes').hidden = !assembly;
      $('#trans-espera').hidden = !assembly;
    }
    $$('[data-engine]').forEach(b=>b.onclick=()=>{engine=b.dataset.engine;$$('[data-engine]').forEach(x=>x.classList.toggle('on',x===b));syncEngine();});
    syncEngine();
    $$('[data-jump]').forEach(a=>a.onclick=e=>{e.preventDefault();$('#'+a.dataset.jump)?.scrollIntoView({behavior:'smooth',block:'start'});});
    browseHandlers();
    $$('[data-copy]').forEach(b=>b.onclick=async()=>{try{await navigator.clipboard.writeText(b.dataset.copy);message('Copiado.');}catch{message('No se pudo copiar.');}});
    $('#panel-start').onclick=async()=>{try{message((await api('/app/api/panel/start',{})).mensaje);}catch(e){message(e.message);}};
    $('#panel-check').onclick=async()=>{try{await api('/estado');message('El panel está activo.');}catch{message('El panel no está activo.');}};
    $('#save-criteria').onclick=async()=>{try{await api('/app/api/criteria',{texto:$('#criteria').value});message('Criterios guardados.');}catch(e){message(e.message);}};
    $('#update-criteria').onclick=async()=>{try{const d=await api('/app/api/update-criteria',{actuales:$('#criteria').value,key:$('#llm-key').value});$('#criteria').value=d.texto;message('Propuesta lista. Revisa y guarda los criterios.');}catch(e){message(e.message);}};
    $('#clean-temp').onclick=async()=>{try{const d=await api('/app/api/clean-preview');if(!d.categorias.length){message('No hay temporales para limpiar.');return;}const ids=prompt('Categorías: '+d.categorias.map(x=>`${x.id} (${x.bytes} bytes)`).join(', ')+'\nIDs separados por coma:');if(ids){const r=await api('/app/api/clean',{ids:ids.split(',').map(x=>x.trim())});message(`Eliminados ${r.archivos} archivos (${r.bytes} bytes).`);}}catch(e){message(e.message);}};
  }
  function browseHandlers() {
    $$('[data-browse]').forEach(b=>b.onclick=async()=>{try{const input=$(`[data-config="${b.dataset.browse}"]`),d=await api('/api/seleccionar/carpeta',{inicial:input.value});if(!d.cancelado)input.value=d.ruta;}catch(e){message(e.message);}});
  }
  function message(text) { $('#config-msg').textContent = text; }
  function values() {
    const d={};
    $$('[data-config]').forEach(x=>{let v=x.value;if(['ASSEMBLYAI_TERMINOS','ASSEMBLYAI_MODELOS'].includes(x.dataset.config))v=v.split(',').map(s=>s.trim()).filter(Boolean);d[x.dataset.config]=v;});
    $$('[data-switch]').forEach(x=>d[x.dataset.switch]=x.getAttribute('aria-checked')==='true');
    d.TRANSCRIPCION_MOTOR=engine;
    return d;
  }
  function showTab(tab) {
    $('#v-gen').hidden=tab!=='general';$('#v-adv').hidden=tab!=='advanced';
    $('#advanced-label').hidden=tab!=='advanced';
    $$('[data-tab]').forEach(b=>{const active=b.dataset.tab===tab;b.classList.toggle('on',active);b.setAttribute('aria-selected',String(active));});
  }
  document.addEventListener('click',e=>{const b=e.target.closest('[data-switch]');if(!b)return;const active=b.getAttribute('aria-checked')!=='true';b.setAttribute('aria-checked',String(active));b.classList.toggle('off',!active);});
  $$('[data-tab]').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));
  $('#save-config').onclick=async()=>{const tab=$('#v-adv').hidden?'general':'advanced',d=values(),llm=$('#llm-key')?.value,assembly=$('#assembly-key')?.value;if(llm)d.API_KEY=llm;if(assembly)d.ASSEMBLYAI_API_KEY=assembly;try{await api('/app/api/config',d);message('Configuración guardada.');await load();showTab(tab);}catch(e){for(const [k,v] of Object.entries(e.errors||{})){const x=$(`[data-config="${k}"]`);if(x)x.setCustomValidity(v);}message(e.message);}};
  $('#test-obs').onclick=async()=>{try{message((await api('/api/probar/obs',{})).mensaje);}catch(e){message(e.message);}};
  $('#test-ai').onclick=async()=>{try{message((await api('/app/api/test-ai',{key:$('#llm-key')?.value||''})).mensaje);}catch(e){message(e.message);}};
  async function load() {
    try {
      cfg=await api('/app/api/config');engine=cfg.TRANSCRIPCION_MOTOR||'whisper_local';
      general();advanced();
      api('/app/api/criteria').then(d=>{const x=$('#criteria');if(x)x.value=d.texto||'';}).catch(()=>{});
    } catch(e) { message(e.message); }
  }
  load();
  api("/app/api/version").then(d=>{const x=$("#config-version");if(x)x.textContent="v"+d.version;}).catch(()=>{});
})();
