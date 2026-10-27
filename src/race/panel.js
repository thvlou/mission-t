import { VEHICLES, getVehicle } from '../vehicles.js';
import { COURSES, courseOf } from './courses.js';

// The Race tab's right-hand panel (room list → room with Ready / Start) and the driver card where
// each player picks a nickname and a car. Rendering is plain HTML strings; clicks are delegated.
const PROFILE_KEY = 'vertigo:driver';
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

export function loadProfile() {
  try {
    const p = JSON.parse(localStorage.getItem(PROFILE_KEY));
    if (p && typeof p.nick === 'string') return { nick: p.nick, car: getVehicle(p.car).id };
  } catch { /* nothing saved */ }
  return null;
}

export function saveProfile(p) {
  try { localStorage.setItem(PROFILE_KEY, JSON.stringify(p)); } catch { /* storage unavailable */ }
}

export class RacePanel {
  // actions: { onProfile(profile), onCopy() , fmtKm(id) → string|null, fmtResult(row) → string|null }
  constructor(el, race, actions) {
    this.el = el;
    this.race = race;
    this.actions = actions;
    this.lastHtml = '';
    this.card = buildDriverCard();
    document.body.append(this.card);
    this.afterSave = null;
    el.addEventListener('click', (e) => this.click(e));
    this.card.addEventListener('click', (e) => this.cardClick(e));
    this.card.querySelector('input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); this.saveDriver(); }
      if (e.key === 'Escape') { e.preventDefault(); this.closeDriver(); }
    });
  }

  get driverOpen() {
    return !this.card.hidden;
  }

  // Driver card: nickname + car. `then` runs after Save (e.g. join the linked room).
  openDriver(then = null) {
    const p = this.race.profile;
    this.afterSave = then;
    this.pick = p.car;
    this.card.querySelector('input').value = p.nick;
    this.paintCars();
    this.card.hidden = false;
    setTimeout(() => this.card.querySelector('input').focus(), 30);
  }

  closeDriver() {
    this.card.hidden = true;
    this.afterSave = null;
  }

  saveDriver() {
    const nick = this.card.querySelector('input').value.replace(/[<>]/g, '').trim().slice(0, 14);
    if (!nick) {
      this.card.querySelector('input').focus();
      this.card.querySelector('.driver-note').textContent = 'Pick a nickname first';
      return;
    }
    const profile = { nick, car: this.pick };
    saveProfile(profile);
    this.card.hidden = true;
    this.actions.onProfile(profile);
    const then = this.afterSave;
    this.afterSave = null;
    then?.();
    this.render(true);
  }

  paintCars() {
    this.card.querySelector('.car-grid').innerHTML = VEHICLES.map((v) => `
      <button type="button" data-car="${esc(v.id)}" class="${v.id === this.pick ? 'on' : ''}" aria-pressed="${v.id === this.pick}">
        <img src="${esc(v.preview)}" alt="" loading="lazy">
        <b>${esc(v.name)}</b>
        <small><i style="background:${esc(v.hex)}"></i>${esc(v.color)}</small>
      </button>`).join('');
    this.card.querySelector('.driver-note').textContent = 'Every car drives the same; only the looks change.';
  }

  cardClick(e) {
    const car = e.target.closest('[data-car]');
    if (car) {
      this.pick = car.dataset.car;
      this.paintCars();
      return;
    }
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'save') this.saveDriver();
    else if (act === 'cancel') this.closeDriver();
  }

  click(e) {
    const btn = e.target.closest('[data-act]');
    if (!btn || btn.disabled) return;
    const r = this.race;
    const act = btn.dataset.act;
    btn.blur();
    if (act === 'driver') this.openDriver();
    else if (act === 'create') this.ensureDriver(() => r.enter(''));
    else if (act === 'join') this.ensureDriver(() => r.enter(btn.dataset.code));
    else if (act === 'leave' || act === 'back') r.browse();
    else if (act === 'copy') this.actions.onCopy(btn);
    else if (act === 'ready') r.setReady(!r.me?.ready);
    else if (act === 'start') r.start();
    else if (act === 'course') r.setCourse(btn.dataset.course);
  }

  // A first-time player names themselves before joining anything.
  ensureDriver(then) {
    if (this.race.profile.nick) then();
    else this.openDriver(then);
  }

  render(force = false) {
    const html = this.html();
    if (!force && html === this.lastHtml) return;
    this.lastHtml = html;
    this.el.innerHTML = html;
  }

  html() {
    const r = this.race;
    const prof = r.profile;
    const car = getVehicle(prof.car);
    const driver = `<button type="button" class="driver-chip" data-act="driver" title="Change nickname or car">
        <i style="background:${esc(car.hex)}"></i><span>${esc(prof.nick || 'Set your name')}</span><small>${esc(car.name)}</small><em>Edit</em>
      </button>`;

    if (r.phase === 'browse' || r.phase === 'offline') {
      const rows = r.rooms.map((room) => {
        const full = room.players >= room.max;
        const state = full ? 'Full' : room.phase === 'lobby' ? 'Waiting' : 'Racing';
        return `<li><button type="button" data-act="join" data-code="${esc(room.code)}" ${full ? 'disabled' : ''}>
            <b>${esc(room.code)}</b><span>${esc(room.host)}<small>${esc(courseOf(room.course).name)}</small></span><span>${room.players}/${room.max}</span><em class="${state.toLowerCase()}">${state}</em>
          </button></li>`;
      }).join('');
      const empty = r.listOk ? 'No rooms yet — create one' : 'Connecting to the room list…';
      return `<div class="race-head"><span class="eyebrow">Race</span><strong>Rooms</strong><button type="button" class="link" data-act="create">Create room</button></div>
        ${driver}
        <ol class="room-list">${rows || `<li class="empty">${empty}</li>`}</ol>
        <p class="race-status">${esc(r.notice || 'Free drive while you pick a room')}</p>`;
    }

    if (['connecting', 'error', 'full', 'limit'].includes(r.phase)) {
      const msg = {
        connecting: 'Joining…',
        error: 'Can’t reach the race server',
        full: `Room ${r.room} is full`,
        limit: 'Races are paused for today · back at 09:00 KST',
      }[r.phase];
      return `<div class="race-head"><span class="eyebrow">Room</span><strong>${esc(r.room || '—')}</strong></div>
        <p class="race-status">${esc(msg)}</p>
        ${r.phase === 'connecting' ? '' : '<button type="button" class="race-cta" data-act="back">Back to rooms</button>'}`;
    }

    // In a room: lobby, countdown, racing or finished
    const racing = r.phase === 'countdown' || r.phase === 'racing';
    const rows = [...r.roster].sort((a, b) => a.slot - b.slot).map((p) => {
      const mine = p.id === r.id;
      let right = p.ready ? 'Ready' : p.host ? 'Host' : '—';
      const res = r.results.find((x) => x.id === p.id);
      if (racing || r.phase === 'finished') right = this.actions.fmtResult(res) || this.actions.fmtKm(p.id) || '';
      return `<li class="${mine ? 'me' : ''}${p.ready && !racing ? ' ready' : ''}">
          <i style="background:${esc(getVehicle(p.car).hex)}"></i>
          <span>${esc(p.name)}${p.host ? ' <sup>host</sup>' : ''}</span>
          <small>${esc(getVehicle(p.car).name)}</small>
          <span>${esc(right)}</span>
        </li>`;
    }).join('');
    let cta = '';
    if (r.phase === 'lobby') {
      if (r.isHost) {
        const waiting = r.waitingFor.length;
        cta = `<button type="button" class="race-cta primary" data-act="start" ${waiting ? 'disabled' : ''}>${waiting ? `Waiting for ${waiting} to get ready` : 'Start race ↵'}</button>`;
      } else {
        cta = `<button type="button" class="race-cta ${r.me?.ready ? '' : 'primary'}" data-act="ready">${r.me?.ready ? 'Cancel ready' : 'Ready ↵'}</button>`;
      }
    }
    const status = r.notice || {
      lobby: r.isHost ? 'Everyone else presses Ready, then you start' : 'Press Ready · the host starts the race',
      countdown: 'Get ready',
      racing: r.inRace ? '' : 'Race in progress · you join the next one',
      finished: 'Race over · Enter to go back to the room',
    }[r.phase] || '';
    // Course: the host picks it in the lobby; everyone else sees it.
    const course = courseOf(r.course);
    const coursePick = r.phase === 'lobby' && r.isHost
      ? `<div class="course-pick" role="group" aria-label="Course">${Object.values(COURSES).map((c) => `
          <button type="button" data-act="course" data-course="${esc(c.id)}" class="${c.id === course.id ? 'on' : ''}" aria-pressed="${c.id === course.id}">
            <b>${esc(c.name)}</b><small>${esc(c.note)}</small></button>`).join('')}</div>`
      : `<p class="course-line"><span>Course</span><b>${esc(course.name)}</b><small>${esc(course.note)}</small></p>`;
    return `<div class="race-head"><span class="eyebrow">Room</span><strong>${esc(r.room)}</strong>
        <button type="button" class="link" data-act="copy">Copy link</button>
        ${racing ? '' : '<button type="button" class="link" data-act="leave">Leave</button>'}</div>
      ${coursePick}
      ${r.phase === 'lobby' ? driver : ''}
      <ol class="race-list">${rows}</ol>
      ${cta}
      <p class="race-status" data-live>${esc(status)}</p>`;
  }
}

function buildDriverCard() {
  const el = document.createElement('section');
  el.className = 'driver-card';
  el.hidden = true;
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-label', 'Driver');
  el.innerHTML = `
    <span class="eyebrow">Driver</span>
    <h2>Name and car</h2>
    <label class="nick"><span>Nickname</span><input type="text" maxlength="14" autocomplete="nickname" spellcheck="false" placeholder="Up to 14 letters"></label>
    <div class="car-grid"></div>
    <p class="driver-note"></p>
    <div class="driver-actions">
      <button type="button" class="link" data-act="cancel">Cancel</button>
      <button type="button" class="retry" data-act="save">Save
        <svg class="enter" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 5v8.5H6.5" /><path d="M10.5 9.5 6.5 13.5l4 4" /></svg>
      </button>
    </div>`;
  return el;
}
