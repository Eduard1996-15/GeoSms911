/* ==========================================================================
   GeoSms911 · panel familiar
   ========================================================================== */

'use strict';

/* ---------- Utilidades ---------------------------------------------------- */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const esc = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

function timeAgo(iso) {
  if (!iso) return 'sin datos';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(diff)) return 'sin datos';
  if (diff < 0) return 'ahora';
  if (diff < 15) return 'ahora';
  if (diff < 60) return `hace ${Math.floor(diff)} s`;
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
  return `hace ${Math.floor(diff / 86400)} d`;
}

function formatDateTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('es-UY', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function formatFullDateTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('es-UY', {
    weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

const ICONS = {
  locate: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>',
  ring: '<svg viewBox="0 0 24 24"><path d="M18 15V10a6 6 0 1 0-12 0v5l-2 3h16z"/><path d="M9.5 21a2.5 2.5 0 0 0 5 0"/></svg>',
  stop: '<svg viewBox="0 0 24 24"><path d="M18 15V10a6 6 0 1 0-12 0v5l-2 3h16z"/><path d="M3 3l18 18"/></svg>',
  alert: '<svg viewBox="0 0 24 24"><path d="M12 3 2.6 20h18.8z"/><path d="M12 9v5"/><circle cx="12" cy="17.2" r="0.9" fill="currentColor" stroke="none"/></svg>',
  phone: '<svg viewBox="0 0 24 24"><path d="M5 3h4l2 5-2.5 1.5a12 12 0 0 0 6 6L16 13l5 2v4a2 2 0 0 1-2.2 2A17 17 0 0 1 3 5.2 2 2 0 0 1 5 3z"/></svg>',
  test: '<svg viewBox="0 0 24 24"><path d="M8 3h8M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3"/><path d="M7.5 15h9"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>',
};

const KIND_LABELS = {
  panic: 'Botón de emergencia',
  geofence_exit: 'Salió de una zona segura',
  geofence_enter: 'Entró a una zona segura',
  low_battery: 'Batería baja',
  test: 'Alerta de prueba',
};

const STATUS_LABELS = {
  open: 'Abierta',
  acknowledged: 'Confirmada',
  resolved: 'Resuelta',
  false_alarm: 'Falsa alarma',
};

const COMMAND_INFO = {
  locate: { label: 'Localizar', icon: 'locate', confirm: null },
  ring: {
    label: 'Timbre', icon: 'ring',
    confirm: { title: 'Activar la alarma', text: 'El teléfono de {name} sonará a volumen máximo aunque esté en silencio. ¿Continuar?', ok: 'Activar alarma' },
  },
  stop_ring: { label: 'Silenciar', icon: 'stop', confirm: null },
  alert_screen: {
    label: 'Aviso', icon: 'alert',
    confirm: { title: 'Mostrar pantalla de emergencia', text: 'Se abrirá una pantalla a todo color en el teléfono de {name} con los botones para llamar al 911 y compartir ubicación. ¿Continuar?', ok: 'Enviar aviso' },
  },
  call: {
    label: 'Llamar', icon: 'phone',
    confirm: { title: 'Puente telefónico', text: 'Twilio llamará a tu teléfono y al de {name}, y los unirá en una llamada. Atiende tu teléfono. ¿Continuar?', ok: 'Iniciar llamada' },
  },
  test: {
    label: 'Probar', icon: 'test',
    confirm: { title: 'Simular una alerta', text: 'Se generará una alerta de prueba y se enviará el SMS de notificación real. Útil para verificar que todo funciona.', ok: 'Simular alerta' },
  },
};

/* ---------- Estado -------------------------------------------------------- */

const STORAGE = {
  token: 'geosms911_token',
  device: 'geosms911_device',
  muted: 'geosms911_muted',
};

const state = {
  token: localStorage.getItem(STORAGE.token) || '',
  user: null,
  devices: [],
  activeDeviceId: localStorage.getItem(STORAGE.device) || null,
  alerts: [],
  messages: [],
  zones: [],
  trail: [],
  trailVisible: true,
  addZoneMode: false,
  zonePoint: null,
  soundOn: localStorage.getItem(STORAGE.muted) !== '1',
  dismissedBanners: new Set(),
  ws: null,
  wsRetry: 0,
  audioCtx: null,
  pairExpiresAt: null,
  loading: false,
};

let map = null;
let markersLayer = null;
let zonesLayer = null;
let trailLayer = null;
let timersStarted = false;

/* ---------- Cliente HTTP -------------------------------------------------- */

function errorMessage(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload === 'string') return payload;
  if (typeof payload.detail === 'string') return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail.map((item) => item.msg || '').filter(Boolean).join('. ') || fallback;
  }
  return fallback;
}

async function api(path, { method = 'GET', body, auth = true } = {}) {
  const headers = {};
  if (auth && state.token) headers.Authorization = `Bearer ${state.token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const text = await response.text();
  let payload = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = text; }
  }

  if (response.status === 401 && auth) {
    logout();
    throw new Error('La sesión venció. Vuelve a entrar.');
  }
  if (!response.ok) {
    throw new Error(errorMessage(payload, `Error ${response.status}`));
  }
  return payload;
}

/* ---------- Avisos flotantes --------------------------------------------- */

function toast(title, message = '', type = 'info', timeout = 5500) {
  const node = document.createElement('div');
  node.className = `toast ${type}`;
  node.innerHTML = `
    <span class="toast-icon">${type === 'alert' ? '!' : type === 'success' ? '✓' : type === 'error' ? '×' : 'i'}</span>
    <div><strong>${esc(title)}</strong>${message ? `<p>${esc(message)}</p>` : ''}</div>`;
  $('#toasts').appendChild(node);
  setTimeout(() => {
    node.style.opacity = '0';
    node.style.transition = 'opacity .25s';
    setTimeout(() => node.remove(), 260);
  }, timeout);
}

function beep() {
  if (!state.soundOn) return;
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!state.audioCtx) state.audioCtx = new Ctx();
    const ctx = state.audioCtx;
    if (ctx.state === 'suspended') ctx.resume();
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, now);
    osc.frequency.setValueAtTime(640, now + 0.2);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.22, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.65);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.7);
  } catch { /* sin audio disponible */ }
}

/* ---------- Sesión -------------------------------------------------------- */

function showLogin() {
  $('#app-view').hidden = true;
  $('#login-view').hidden = false;
  $('#auth-error').hidden = true;
  $('#password').value = '';
}

function renderUser() {
  if (!state.user) return;
  const name = state.user.name || state.user.email;
  $('#user-name').textContent = name;
  $('#user-phone').textContent = state.user.phone || 'Sin teléfono';
  $('#user-avatar').textContent = (name || '?').trim().charAt(0).toUpperCase();
}

function logout() {
  state.token = '';
  state.user = null;
  localStorage.removeItem(STORAGE.token);
  if (state.ws) {
    try { state.ws.close(); } catch { /* ignorar */ }
    state.ws = null;
  }
  showLogin();
}

let authMode = 'login';

function setAuthMode(mode) {
  authMode = mode;
  const registering = mode === 'register';
  $('#auth-title').textContent = registering ? 'Crear cuenta de tutor' : 'Entrar al panel';
  $('#auth-subtitle').textContent = registering
    ? 'Solo necesitas un correo y tu teléfono.'
    : 'Usa la cuenta del tutor.';
  $('#name-field').hidden = !registering;
  $('#phone-field').hidden = !registering;
  $('#auth-submit').textContent = registering ? 'Crear cuenta' : 'Entrar';
  $('#auth-toggle').textContent = registering ? 'Ya tengo cuenta' : 'Crear una cuenta nueva';
  $('#auth-error').hidden = true;
  $('#password').setAttribute('autocomplete', registering ? 'new-password' : 'current-password');
}

async function submitAuth(event) {
  event.preventDefault();
  const email = $('#email').value.trim();
  const password = $('#password').value;
  const errorBox = $('#auth-error');
  errorBox.hidden = true;

  const submit = $('#auth-submit');
  submit.disabled = true;
  submit.textContent = authMode === 'register' ? 'Creando…' : 'Entrando…';

  try {
    const payload = { email, password };
    if (authMode === 'register') {
      payload.name = $('#name').value.trim() || 'Tutor';
      const phone = $('#phone').value.trim();
      if (phone) payload.phone = phone;
    }
    const data = await api(`/api/auth/${authMode}`, { method: 'POST', body: payload, auth: false });
    state.token = data.access_token;
    state.user = data.user;
    localStorage.setItem(STORAGE.token, state.token);
    await enterApp();
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  } finally {
    submit.disabled = false;
    submit.textContent = authMode === 'register' ? 'Crear cuenta' : 'Entrar';
  }
}

/* ---------- Arranque ------------------------------------------------------ */

async function enterApp() {
  $('#login-view').hidden = true;
  $('#app-view').hidden = false;
  renderUser();
  initMap();
  await refreshAll();
  if (!state.user.phone) {
    toast(
      'Falta tu teléfono',
      'Agrégalo en tu perfil para recibir las alertas por SMS y usar el comando LLAMAR.',
      'alert',
      9000,
    );
  }
  connectWs();
  startTimers();
  setTimeout(() => map && map.invalidateSize(), 80);
}

async function refreshAll() {
  if (state.loading) return;
  state.loading = true;
  try {
    await loadDevices();
    await Promise.all([loadAlerts(), loadMessages(), loadZones()]);
    if (state.activeDeviceId) {
      await loadTrail(state.activeDeviceId);
    }
    renderAll();
  } catch (error) {
    toast('No se pudo cargar la información', error.message, 'error');
  } finally {
    state.loading = false;
  }
}

async function loadDevices() {
  const data = await api('/api/devices');
  state.devices = data.devices || [];

  const stillExists = state.devices.some((device) => device.id === state.activeDeviceId);
  if (!stillExists) {
    state.activeDeviceId = state.devices[0]?.id || null;
    if (state.activeDeviceId) localStorage.setItem(STORAGE.device, state.activeDeviceId);
    else localStorage.removeItem(STORAGE.device);
  }
}

async function loadAlerts() {
  const data = await api('/api/alerts?limit=60');
  state.alerts = data.alerts || [];
}

async function loadMessages() {
  const data = await api('/api/messages?limit=60');
  state.messages = data.messages || [];
  $('#twilio-warning').hidden = Boolean(data.twilio_configured);
}

async function loadZones() {
  const data = await api('/api/geofences');
  state.zones = data.geofences || [];
}

async function loadTrail(deviceId) {
  try {
    const data = await api(`/api/devices/${deviceId}/locations?hours=24&limit=1500`);
    state.trail = (data.points || []).map((point) => [point.lat, point.lng]);
  } catch {
    state.trail = [];
  }
}

/* ---------- Render -------------------------------------------------------- */

function renderAll() {
  renderDevices();
  renderDeviceCard();
  renderAlerts();
  renderMessages();
  renderZones();
  renderBanner();
  renderMap();
}

function activeDevice() {
  return state.devices.find((device) => device.id === state.activeDeviceId) || null;
}

function renderDevices() {
  const container = $('#device-list');
  if (!state.devices.length) {
    container.innerHTML = '<div class="list-empty">Todavía no hay teléfonos emparejados.<br>Usa “+ Emparejar” para agregar el primero.</div>';
    return;
  }

  container.innerHTML = state.devices.map((device) => `
    <button class="device-item ${device.id === state.activeDeviceId ? 'is-active' : ''}" data-device-id="${esc(device.id)}" type="button">
      <i class="dot ${device.online ? 'dot-online' : 'dot-offline'}"></i>
      <span class="device-item-text">
        <strong>${esc(device.name)}</strong>
        <small>${device.online ? 'En línea' : `Visto ${timeAgo(device.last_seen_at)}`} · ${device.last_battery ?? '?'}%</small>
      </span>
    </button>`).join('');
}

function batteryClass(level) {
  if (level === null || level === undefined) return '';
  if (level < 15) return 'critical';
  if (level < 30) return 'low';
  return '';
}

function renderDeviceCard() {
  const container = $('#device-card');
  const device = activeDevice();

  if (!device) {
    container.innerHTML = `
      <div class="device-card-head">
        <div class="device-card-title">
          <h2>Sin teléfonos</h2>
          <small>Empareja el teléfono de tu hijo para comenzar.</small>
        </div>
      </div>
      <button class="btn btn-primary btn-block" data-action="pair" type="button">Emparejar un teléfono</button>`;
    return;
  }

  const lastFix = device.last_location_at
    ? `${formatDateTime(device.last_location_at)}${device.last_accuracy != null ? ` · ±${Math.round(device.last_accuracy)} m` : ''}`
    : 'Sin ubicación todavía';
  const battery = device.last_battery;

  container.innerHTML = `
    <div class="device-card-head">
      <div class="device-card-title">
        <h2>${esc(device.name)}</h2>
        <small>${esc(device.model_name || 'Android')} · app ${esc(device.app_version || '—')}</small>
      </div>
      <span class="device-state ${device.online ? 'online' : 'offline'}">${device.online ? 'En línea' : 'Sin conexión'}</span>
    </div>

    <div class="device-metrics">
      <div class="metric">
        <span>Batería</span>
        <strong>${battery != null ? `${battery}%` : 'Sin dato'}</strong>
        <div class="battery-bar"><i class="${batteryClass(battery)}" style="width:${battery != null ? clamp(battery, 0, 100) : 0}%"></i></div>
      </div>
      <div class="metric">
        <span>Última conexión</span>
        <strong>${device.online ? 'Ahora' : timeAgo(device.last_seen_at)}</strong>
        <small class="metric-note"><i class="dot ${device.online ? 'dot-online' : 'dot-offline'}"></i>${device.online ? 'Conectado' : 'Sin señal'}</small>
      </div>
    </div>

    <div class="metric">
      <span>Última ubicación</span>
      <strong>${esc(lastFix)}</strong>
    </div>

    ${!device.location_sharing ? '<p class="muted small">La ubicación está desactivada desde el teléfono.</p>' : ''}

    <div class="command-grid">
      ${commandButton('locate')}
      ${commandButton('ring')}
      ${commandButton('alert_screen')}
      ${commandButton('call')}
      ${commandButton('stop_ring')}
      ${commandButton('test')}
    </div>

    <div class="device-card-foot">
      <button class="btn btn-ghost btn-xs" data-action="pair" type="button">+ Otro teléfono</button>
      <button class="link-danger" data-action="revoke" type="button">Desvincular</button>
    </div>`;
}

function commandButton(kind) {
  const info = COMMAND_INFO[kind];
  const extra = kind === 'ring' || kind === 'alert_screen' ? 'danger' : kind === 'call' ? 'call' : '';
  return `<button class="command-btn ${extra}" data-command="${kind}" type="button" title="${esc(info.label)}">
    ${ICONS[info.icon]}<span>${esc(info.label)}</span>
  </button>`;
}

function renderAlerts() {
  const container = $('#alerts-list');
  const count = state.alerts.filter((alert) => alert.status === 'open').length;
  const badge = $('#alerts-count');
  badge.textContent = String(count);
  badge.classList.toggle('zero', count === 0);

  if (!state.alerts.length) {
    container.innerHTML = '<div class="list-empty">No hay alertas registradas. Todo tranquilo.</div>';
    return;
  }

  container.innerHTML = state.alerts.map((alert) => {
    const actions = [];
    if (alert.status === 'open') {
      actions.push(`<button class="btn btn-ghost btn-xs" data-alert-action="acknowledged" data-alert-id="${esc(alert.id)}" type="button">Confirmar</button>`);
      actions.push(`<button class="btn btn-ghost btn-xs" data-alert-action="resolved" data-alert-id="${esc(alert.id)}" type="button">Resolver</button>`);
    } else if (alert.status === 'acknowledged') {
      actions.push(`<button class="btn btn-ghost btn-xs" data-alert-action="resolved" data-alert-id="${esc(alert.id)}" type="button">Resolver</button>`);
    }
    if (alert.status !== 'false_alarm') {
      actions.push(`<button class="btn btn-ghost btn-xs" data-alert-action="false_alarm" data-alert-id="${esc(alert.id)}" type="button">Falsa alarma</button>`);
    }

    return `<article class="alert-item ${esc(alert.status)}">
      <div class="alert-top">
        <span class="alert-kind">${esc(KIND_LABELS[alert.kind] || alert.kind)}</span>
        <span class="alert-time" title="${esc(formatFullDateTime(alert.created_at))}">${esc(timeAgo(alert.created_at))}</span>
      </div>
      <div class="alert-sub">
        ${esc(alert.device_name || '')} · <span class="chip ${esc(alert.status)}">${esc(STATUS_LABELS[alert.status] || alert.status)}</span>
        ${alert.battery != null ? ` · ${alert.battery}%` : ''}
      </div>
      ${alert.message ? `<div class="alert-sub">${esc(alert.message)}</div>` : ''}
      ${alert.maps_url ? `<div class="alert-sub"><a href="${esc(alert.maps_url)}" target="_blank" rel="noopener noreferrer">Abrir ubicación en el mapa</a></div>` : ''}
      <div class="alert-actions">${actions.join('')}</div>
    </article>`;
  }).join('');
}

function renderMessages() {
  const container = $('#messages-list');
  if (!state.messages.length) {
    container.innerHTML = '<div class="list-empty">Sin mensajes. Aquí verás los SMS enviados y recibidos.</div>';
    return;
  }

  container.innerHTML = state.messages.map((message) => {
    const inbound = message.direction === 'inbound';
    const status = message.status || 'enviado';
    return `<article class="message-item ${inbound ? 'inbound' : ''}">
      <div class="message-meta">
        <span>${inbound ? 'Recibido' : 'Enviado'}${inbound ? ` · ${esc(message.from_number || '')}` : ` · ${esc(message.to || '')}`}</span>
        <span><i class="status-dot ${esc(status)}"></i> ${esc(status)}</span>
      </div>
      <div class="message-body">${esc(message.body)}</div>
      <div class="message-meta"><span>${esc(formatDateTime(message.created_at))}</span>${message.error ? `<span title="${esc(message.error)}">error</span>` : ''}</div>
    </article>`;
  }).join('');
}

function renderZones() {
  const container = $('#zones-list');
  if (!state.zones.length) {
    container.innerHTML = '<div class="list-empty">Sin zonas seguras. Añade “Casa” o “Colegio” para recibir un aviso al salir.</div>';
    return;
  }

  container.innerHTML = state.zones.map((zone) => `
    <div class="zone-item">
      <div class="zone-item-text">
        <strong>${esc(zone.name)}</strong>
        <small>${zone.radius_m} m · ${zone.device_id ? 'un teléfono' : 'todos'} · ${zone.last_state === 'outside' ? 'fuera' : zone.last_state === 'inside' ? 'dentro' : 'sin evaluar'}</small>
      </div>
      <button class="icon-btn" data-zone-delete="${esc(zone.id)}" type="button" title="Eliminar zona">${ICONS.trash}</button>
    </div>`).join('');
}

function renderBanner() {
  const banner = $('#alert-banner');
  const open = state.alerts.find(
    (alert) => alert.status === 'open' && !state.dismissedBanners.has(alert.id),
  );

  if (!open) {
    banner.hidden = true;
    return;
  }

  const device = state.devices.find((item) => item.id === open.device_id);
  $('#alert-banner-title').textContent = `${KIND_LABELS[open.kind] || 'Alerta'} · ${open.device_name || device?.name || ''}`;
  const when = formatFullDateTime(open.created_at);
  const where = open.lat != null ? ' · ubicación disponible' : ' · sin ubicación';
  $('#alert-banner-sub').textContent = `${when}${where}`;
  $('#alert-banner-call').href = `tel:${device?.emergency_number || '911'}`;
  $('#alert-banner-ack').dataset.alertId = open.id;
  banner.hidden = false;
}

/* ---------- Mapa ---------------------------------------------------------- */

function initMap() {
  if (map) return;

  map = L.map('map', {
    zoomControl: false,
    attributionControl: true,
    worldCopyJump: true,
  }).setView([-34.9011, -56.1645], 12);

  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);

  L.control.zoom({ position: 'bottomright' }).addTo(map);

  markersLayer = L.layerGroup().addTo(map);
  zonesLayer = L.layerGroup().addTo(map);
  trailLayer = L.layerGroup().addTo(map);

  map.on('click', (event) => {
    if (!state.addZoneMode) return;
    state.zonePoint = event.latlng;
    openZoneDialog(event.latlng);
  });
}

function deviceIcon(device, isActive) {
  const classes = ['device-pin'];
  if (!device.online) classes.push('offline');
  if (isActive) classes.push('active');
  return L.divIcon({
    className: 'device-pin-wrap',
    html: `<div class="${classes.join(' ')}"></div>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
    popupAnchor: [0, -14],
  });
}

function renderMap() {
  if (!map) return;
  markersLayer.clearLayers();
  zonesLayer.clearLayers();
  trailLayer.clearLayers();

  state.zones.forEach((zone) => {
    const circle = L.circle([zone.lat, zone.lng], {
      radius: zone.radius_m,
      color: zone.last_state === 'outside' ? '#e11d48' : '#38bdf8',
      weight: 1.6,
      fillColor: zone.last_state === 'outside' ? '#e11d48' : '#38bdf8',
      fillOpacity: 0.09,
      dashArray: '5 6',
    });
    circle.bindPopup(
      `<b>${esc(zone.name)}</b><br>Radio ${zone.radius_m} m<br>${zone.last_state === 'outside' ? 'El teléfono está fuera' : 'Zona activa'}`,
    );
    circle.addTo(zonesLayer);
  });

  const withPosition = state.devices.filter((device) => device.last_lat != null && device.last_lng != null);

  withPosition.forEach((device) => {
    const isActive = device.id === state.activeDeviceId;
    const marker = L.marker([device.last_lat, device.last_lng], {
      icon: deviceIcon(device, isActive),
      zIndexOffset: isActive ? 1000 : 0,
    });
    marker.bindPopup(
      `<b>${esc(device.name)}</b><br>${device.online ? 'En línea' : `Visto ${esc(timeAgo(device.last_seen_at))}`}` +
      `<br>Batería ${device.last_battery ?? '?'}%<br><small>${esc(formatDateTime(device.last_location_at))}</small>`,
    );
    marker.on('click', () => selectDevice(device.id));
    marker.addTo(markersLayer);
  });

  const device = activeDevice();
  if (device && device.last_lat != null) {
    const center = [device.last_lat, device.last_lng];
    if (device.last_accuracy) {
      L.circle(center, {
        radius: Math.min(device.last_accuracy, 250),
        color: '#22c55e',
        weight: 1,
        fillColor: '#22c55e',
        fillOpacity: 0.08,
        interactive: false,
      }).addTo(trailLayer);
    }

    if (state.trailVisible && state.trail.length > 1) {
      L.polyline(state.trail, {
        color: '#22c55e',
        weight: 3,
        opacity: 0.55,
        smoothFactor: 1.5,
        interactive: false,
      }).addTo(trailLayer);
    }
  }

  updateMapTimestamp();
}

function updateMapTimestamp() {
  const device = activeDevice();
  const target = $('#map-updated');
  if (!device) {
    target.textContent = 'Sin teléfonos';
    return;
  }
  target.textContent = `Actualizado ${timeAgo(device.last_location_at || device.last_seen_at)}`;
}

function focusActiveDevice(zoom = 16) {
  const device = activeDevice();
  if (!device || device.last_lat == null) {
    if (state.devices.length) toast('Sin ubicación', 'El teléfono todavía no envió su posición.', 'info');
    return;
  }
  map.setView([device.last_lat, device.last_lng], zoom, { animate: true });
}

function selectDevice(deviceId) {
  if (deviceId === state.activeDeviceId) return;
  state.activeDeviceId = deviceId;
  localStorage.setItem(STORAGE.device, deviceId);
  state.trail = [];
  renderDevices();
  renderDeviceCard();
  renderMap();
  loadTrail(deviceId).then(() => {
    renderMap();
    focusActiveDevice();
  });
}

/* ---------- Acciones ------------------------------------------------------ */

async function sendCommand(kind) {
  const device = activeDevice();
  if (!device) return;
  const info = COMMAND_INFO[kind];
  if (!info) return;

  if (info.confirm) {
    const ok = await askConfirm({
      title: info.confirm.title,
      text: info.confirm.text.replace('{name}', device.name),
      okLabel: info.confirm.ok,
      danger: kind === 'ring',
    });
    if (!ok) return;
  }

  try {
    if (kind === 'call') {
      const result = await api(`/api/devices/${device.id}/call`, { method: 'POST' });
      toast('Llamada iniciada', result.message || 'Atiende tu teléfono.', 'success', 8000);
      return;
    }
    if (kind === 'test') {
      await api(`/api/devices/${device.id}/test-alert`, { method: 'POST' });
      toast('Alerta de prueba enviada', 'Se generó la alerta y el SMS de notificación.', 'success');
      await loadAlerts();
      renderAlerts();
      renderBanner();
      return;
    }
    const command = await api(`/api/devices/${device.id}/commands`, {
      method: 'POST',
      body: { kind },
    });
    toast(
      `Orden “${info.label}” enviada`,
      device.online
        ? 'El teléfono la recibirá en los próximos segundos.'
        : 'El teléfono está sin conexión: se envió también por SMS como respaldo.',
      'success',
    );
    if (command.status === 'sent') beep();
  } catch (error) {
    toast('No se pudo enviar la orden', error.message, 'error', 8000);
  }
}

async function updateAlert(alertId, status) {
  try {
    await api(`/api/alerts/${alertId}`, { method: 'POST', body: { status } });
    await loadAlerts();
    renderAlerts();
    renderBanner();
    toast('Alerta actualizada', STATUS_LABELS[status] || status, 'success', 3000);
  } catch (error) {
    toast('No se pudo actualizar', error.message, 'error');
  }
}

async function revokeDevice(device) {
  const ok = await askConfirm({
    title: 'Desvincular teléfono',
    text: `El teléfono “${device.name}” dejará de enviar datos y no aceptará más órdenes. Podrás emparejarlo de nuevo con un código nuevo.`,
    okLabel: 'Desvincular',
    danger: true,
  });
  if (!ok) return;
  try {
    await api(`/api/devices/${device.id}/revoke`, { method: 'POST' });
    toast('Teléfono desvinculado', device.name, 'success');
    state.activeDeviceId = null;
    await refreshAll();
  } catch (error) {
    toast('No se pudo desvincular', error.message, 'error');
  }
}

/* ---------- Diálogos ------------------------------------------------------ */

function askConfirm({ title, text, okLabel = 'Enviar', danger = false }) {
  return new Promise((resolve) => {
    const dialog = $('#confirm-dialog');
    $('#confirm-title').textContent = title;
    $('#confirm-text').textContent = text;
    $('#confirm-ok').textContent = okLabel;
    $('#confirm-ok').className = `btn ${danger ? 'btn-danger' : 'btn-primary'}`;
    dialog.returnValue = '';

    const onClose = () => {
      dialog.removeEventListener('close', onClose);
      resolve(dialog.returnValue === 'confirm');
    };
    dialog.addEventListener('close', onClose);
    dialog.showModal();
  });
}

function openPairDialog() {
  const dialog = $('#pair-dialog');
  $('#pair-code').textContent = '······';
  $('#pair-expiry').textContent = '';
  dialog.showModal();
  generatePairingCode();
}

let pairTimer = null;

async function generatePairingCode() {
  try {
    const data = await api('/api/devices/pairing-code', { method: 'POST', body: {} });
    $('#pair-code').textContent = data.code;
    state.pairExpiresAt = Date.now() + data.expires_in * 1000;
    updatePairExpiry();
    clearInterval(pairTimer);
    pairTimer = setInterval(updatePairExpiry, 1000);
  } catch (error) {
    toast('No se pudo generar el código', error.message, 'error');
  }
}

function updatePairExpiry() {
  if (!state.pairExpiresAt) return;
  const remaining = Math.max(0, Math.floor((state.pairExpiresAt - Date.now()) / 1000));
  if (!remaining) {
    $('#pair-expiry').textContent = 'Código vencido. Genera uno nuevo.';
    clearInterval(pairTimer);
    return;
  }
  const minutes = Math.floor(remaining / 60);
  const seconds = String(remaining % 60).padStart(2, '0');
  $('#pair-expiry').textContent = `Vence en ${minutes}:${seconds}`;
}

function openProfileDialog() {
  if (!state.user) return;
  $('#profile-name').value = state.user.name || '';
  $('#profile-phone').value = state.user.phone || '';
  $('#profile-error').hidden = true;
  $('#profile-dialog').showModal();
}

async function saveProfile(event) {
  event.preventDefault();
  const errorBox = $('#profile-error');
  errorBox.hidden = true;
  try {
    const payload = { name: $('#profile-name').value.trim() };
    const phone = $('#profile-phone').value.trim();
    if (phone) payload.phone = phone;
    const user = await api('/api/auth/me', { method: 'PATCH', body: payload });
    state.user = user;
    renderUser();
    $('#profile-dialog').close();
    toast('Perfil actualizado', user.phone ? 'Recibirás los avisos en ese número.' : 'Falta tu teléfono para los SMS.', 'success');
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  }
}

/* ---------- Zonas --------------------------------------------------------- */

function openZoneDialog(latlng) {
  const point = latlng || (map && map.getCenter()) || { lat: -34.9011, lng: -56.1645 };
  state.zonePoint = point;
  $('#zone-name').value = '';
  $('#zone-radius').value = '300';
  $('#zone-radius-label').textContent = '300 m';
  $('#zone-coords').textContent = `Centro: ${point.lat.toFixed(6)}, ${point.lng.toFixed(6)}`;
  $('#zone-error').hidden = true;

  const select = $('#zone-device');
  select.innerHTML = '<option value="">Todos los teléfonos</option>' + state.devices.map(
    (device) => `<option value="${esc(device.id)}">${esc(device.name)}</option>`,
  ).join('');

  $('#zone-dialog').showModal();
}

async function saveZone(event) {
  event.preventDefault();
  const point = state.zonePoint;
  if (!point) return;
  const errorBox = $('#zone-error');
  errorBox.hidden = true;

  try {
    await api('/api/geofences', {
      method: 'POST',
      body: {
        name: $('#zone-name').value.trim(),
        lat: point.lat,
        lng: point.lng,
        radius_m: Number($('#zone-radius').value),
        device_id: $('#zone-device').value || null,
      },
    });
    $('#zone-dialog').close();
    exitAddZoneMode();
    await loadZones();
    renderZones();
    renderMap();
    toast('Zona segura creada', 'Se avisará si el teléfono sale de ella.', 'success');
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  }
}

async function deleteZone(zoneId) {
  const zone = state.zones.find((item) => item.id === zoneId);
  const ok = await askConfirm({
    title: 'Eliminar zona',
    text: `Se eliminará “${zone?.name || 'la zona'}” y sus avisos de salida.`,
    okLabel: 'Eliminar',
    danger: true,
  });
  if (!ok) return;
  try {
    await api(`/api/geofences/${zoneId}`, { method: 'DELETE' });
    await loadZones();
    renderZones();
    renderMap();
    toast('Zona eliminada', '', 'success', 2500);
  } catch (error) {
    toast('No se pudo eliminar', error.message, 'error');
  }
}

function enterAddZoneMode() {
  if (!map) return;
  state.addZoneMode = true;
  $('#map-hint').hidden = false;
  $('#add-zone-btn').setAttribute('aria-pressed', 'true');
  map.getContainer().style.cursor = 'crosshair';
  switchTab('zones');
}

function exitAddZoneMode() {
  state.addZoneMode = false;
  $('#map-hint').hidden = true;
  $('#add-zone-btn').setAttribute('aria-pressed', 'false');
  if (map) map.getContainer().style.cursor = '';
}

/* ---------- Pestañas ------------------------------------------------------ */

function switchTab(name) {
  $$('.tab').forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  $$('.tab-panel').forEach((panel) => {
    const active = panel.dataset.panel === name;
    panel.classList.toggle('is-active', active);
    panel.hidden = !active;
  });
}

/* ---------- WebSocket ----------------------------------------------------- */

function setConnection(online, label) {
  const node = $('#conn-status');
  node.dataset.state = online ? 'on' : 'off';
  $('#conn-label').textContent = label;
}

function connectWs() {
  if (!state.token) return;
  if (state.ws) {
    try { state.ws.close(); } catch { /* ignorar */ }
  }

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${protocol}//${location.host}/ws?token=${encodeURIComponent(state.token)}`);
  state.ws = socket;

  socket.addEventListener('open', () => {
    state.wsRetry = 0;
    setConnection(true, 'En vivo');
  });

  socket.addEventListener('message', (event) => {
    try {
      handleEvent(JSON.parse(event.data));
    } catch { /* mensaje inválido */ }
  });

  socket.addEventListener('close', () => {
    setConnection(false, 'Reconectando…');
    if (!state.token) return;
    state.wsRetry = Math.min(state.wsRetry + 1, 6);
    setTimeout(connectWs, 1000 * state.wsRetry);
  });

  socket.addEventListener('error', () => socket.close());
}

let messageRefresh = null;

function handleEvent(event) {
  const data = event.data || {};

  switch (event.type) {
    case 'location': {
      const device = state.devices.find((item) => item.id === data.device_id);
      if (device) {
        device.last_lat = data.lat;
        device.last_lng = data.lng;
        device.last_accuracy = data.accuracy;
        device.last_battery = data.battery ?? device.last_battery;
        device.last_location_at = data.created_at;
        device.last_seen_at = data.created_at;
        device.online = true;
        if (device.id === state.activeDeviceId) {
          const last = state.trail[state.trail.length - 1];
          if (!last || last[0] !== data.lat || last[1] !== data.lng) {
            state.trail.push([data.lat, data.lng]);
            if (state.trail.length > 1500) state.trail.shift();
          }
        }
        renderDevices();
        renderDeviceCard();
        renderMap();
      }
      break;
    }
    case 'alert': {
      loadAlerts().then(renderAlerts).then(renderBanner);
      renderBanner();
      if (data.status === 'open') {
        beep();
        toast(
          `Alerta: ${KIND_LABELS[data.kind] || data.kind}`,
          `${data.device_name || 'Teléfono'}${data.lat != null ? ' · ubicación recibida' : ''}`,
          'alert',
          9000,
        );
      }
      break;
    }
    case 'message':
      clearTimeout(messageRefresh);
      messageRefresh = setTimeout(() => loadMessages().then(renderMessages), 350);
      break;
    case 'device':
      loadDevices().then(() => {
        renderDevices();
        renderDeviceCard();
        renderMap();
      });
      break;
    case 'command': {
      if (data.status === 'acked') {
        toast('Orden confirmada', `${COMMAND_INFO[data.kind]?.label || data.kind} · ${data.device_id ? 'teléfono conectado' : ''}`, 'success', 3500);
      }
      if (data.status === 'failed') {
        toast('La orden falló', data.error || 'El teléfono no pudo ejecutarla.', 'error');
      }
      break;
    }
    case 'geofence':
      loadZones().then(() => { renderZones(); renderMap(); });
      break;
    default:
      break;
  }
}

/* ---------- Temporizadores ------------------------------------------------ */

function startTimers() {
  if (timersStarted) return;
  timersStarted = true;

  setInterval(() => {
    loadDevices()
      .then(() => { renderDevices(); renderDeviceCard(); renderMap(); })
      .catch(() => {});
    loadAlerts().then(() => { renderAlerts(); renderBanner(); }).catch(() => {});
  }, 60000);

  setInterval(() => {
    renderDevices();
    renderDeviceCard();
    updateMapTimestamp();
    $$('.alert-time').forEach((node) => {
      const iso = node.getAttribute('title');
      if (iso) node.textContent = timeAgo(new Date(iso).toISOString());
    });
  }, 30000);
}

/* ---------- Eventos ------------------------------------------------------- */

function bindEvents() {
  $('#auth-form').addEventListener('submit', submitAuth);
  $('#auth-toggle').addEventListener('click', () => setAuthMode(authMode === 'login' ? 'register' : 'login'));
  $('#logout-btn').addEventListener('click', logout);
  $('#profile-btn').addEventListener('click', openProfileDialog);
  $('#profile-form').addEventListener('submit', saveProfile);

  $('#pair-btn').addEventListener('click', openPairDialog);
  $('#pair-generate').addEventListener('click', generatePairingCode);

  $('#device-card').addEventListener('click', (event) => {    const commandBtn = event.target.closest('[data-command]');
    if (commandBtn) {
      sendCommand(commandBtn.dataset.command);
      return;
    }
    const actionBtn = event.target.closest('[data-action]');
    if (actionBtn) {
      if (actionBtn.dataset.action === 'pair') openPairDialog();
      if (actionBtn.dataset.action === 'revoke') {
        const device = activeDevice();
        if (device) revokeDevice(device);
      }
    }
  });

  $('#device-list').addEventListener('click', (event) => {
    const item = event.target.closest('[data-device-id]');
    if (item) selectDevice(item.dataset.deviceId);
  });

  $$('.tab').forEach((tab) => tab.addEventListener('click', () => switchTab(tab.dataset.tab)));

  $$('[data-close]').forEach((button) => {
    button.addEventListener('click', () => {
      const dialog = button.closest('dialog');
      if (dialog) dialog.close('cancel');
    });
  });

  $('#alerts-list').addEventListener('click', (event) => {
    const btn = event.target.closest('[data-alert-action]');
    if (btn) updateAlert(btn.dataset.alertId, btn.dataset.alertAction);
  });

  $('#zones-list').addEventListener('click', (event) => {
    const btn = event.target.closest('[data-zone-delete]');
    if (btn) deleteZone(btn.dataset.zoneDelete);
  });

  $('#alert-banner-ack').addEventListener('click', (event) => {
    const id = event.currentTarget.dataset.alertId;
    if (id) updateAlert(id, 'acknowledged');
  });

  $('#alert-banner-close').addEventListener('click', () => {
    const open = state.alerts.find((alert) => alert.status === 'open');
    if (open) state.dismissedBanners.add(open.id);
    $('#alert-banner').hidden = true;
  });

  $('#mute-btn').addEventListener('click', () => {
    state.soundOn = !state.soundOn;
    localStorage.setItem(STORAGE.muted, state.soundOn ? '0' : '1');
    $('#mute-btn').setAttribute('aria-pressed', state.soundOn ? 'false' : 'true');
    if (state.soundOn) beep();
  });

  $('#refresh-alerts').addEventListener('click', () => {
    loadAlerts().then(() => { renderAlerts(); renderBanner(); }).catch((error) => toast('Error', error.message, 'error'));
  });

  $('#test-sms-btn').addEventListener('click', async () => {
    try {
      const log = await api('/api/messages/test', { method: 'POST', body: { body: 'Prueba de GeoSms911 desde el panel.' } });
      await loadMessages();
      renderMessages();
      toast(
        log.status === 'failed' ? 'No se envió' : 'SMS de prueba',
        log.error || 'Revisa el registro de mensajes.',
        log.status === 'failed' ? 'error' : 'success',
      );
    } catch (error) {
      toast('No se pudo enviar el SMS', error.message, 'error', 8000);
    }
  });

  $('#add-zone-btn').addEventListener('click', () => {
    if (state.addZoneMode) exitAddZoneMode();
    else enterAddZoneMode();
  });

  $('#zones-add-btn').addEventListener('click', () => {
    switchTab('zones');
    if (state.addZoneMode) openZoneDialog(state.zonePoint || map.getCenter());
    else enterAddZoneMode();
  });

  $('#zone-form').addEventListener('submit', saveZone);
  $('#zone-radius').addEventListener('input', (event) => {
    $('#zone-radius-label').textContent = `${event.target.value} m`;
  });
  $('#zone-dialog').addEventListener('close', () => exitAddZoneMode());

  $('#fit-btn').addEventListener('click', () => focusActiveDevice());

  $('#trail-btn').addEventListener('click', () => {
    state.trailVisible = !state.trailVisible;
    $('#trail-btn').setAttribute('aria-pressed', state.trailVisible ? 'true' : 'false');
    renderMap();
  });

  window.addEventListener('resize', () => map && map.invalidateSize());
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && state.token && !state.ws) connectWs();
  });
}

/* ---------- Inicio -------------------------------------------------------- */

async function init() {
  bindEvents();
  setAuthMode('login');
  $('#server-url').textContent = location.origin;
  $('#mute-btn').setAttribute('aria-pressed', state.soundOn ? 'false' : 'true');

  if (!state.token) {
    showLogin();
    return;
  }

  try {
    state.user = await api('/api/auth/me');
    await enterApp();
  } catch {
    state.token = '';
    localStorage.removeItem(STORAGE.token);
    showLogin();
  }
}

document.addEventListener('DOMContentLoaded', init);
