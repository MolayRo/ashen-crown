// 关前整备：出击、出击人员、调整站位、物品、商店、部队（加点）、目标、存档、设置
import { W, H } from '../core/renderer.js';
import { fill, drawWindow, drawPointer } from '../core/gfx.js';
import { drawText, wrapText } from '../core/font.js';
import { audio } from '../core/audio.js';
import { ListMenu } from '../ui/menu.js';
import { CHARACTERS } from '../game/data/characters.js';
import { CLASSES } from '../game/data/classes.js';
import { ITEMS, makeItem } from '../game/data/items.js';
import { BattleState, MAX_ITEMS } from '../game/battle.js';
import { currentChapter } from '../game/flow.js';
import * as R from '../game/rules.js';
import { drawMini, drawIcon } from './map/hud.js';
import { MapView, TS } from './map/view.js';
import { UnitInfoScene } from './unitinfo.js';
import { ItemMenuScene, TradeScene, ConvoyScene } from './items.js';
import { SaveLoadScene } from './saveload.js';
import { SettingsScene } from './settings.js';
import { ConfirmDialog } from './confirm.js';
import { ObjectiveScene } from './map/mapscene.js';
import { startBattle, toTitle, autosave } from './flowctl.js';
import { autoPrep } from '../game/autoplay.js';

export function rosterUnit(c, id) {
  const r = c.roster[id];
  r.portrait = CHARACTERS[id].portrait;
  r.team = 'player';
  r.model = CLASSES[r.cls].model;
  r.hp = r.mhp;
  return r;
}

export class PrepScene {
  constructor() {
    this.menu = new ListMenu([
      { label: '出击', value: 'go' },
      { label: '出击人员', value: 'deploy' },
      { label: '调整站位', value: 'formation' },
      { label: '物品整理', value: 'items' },
      { label: '商店', value: 'shop' },
      { label: '部队 · 加点', value: 'units' },
      { label: '查看目标', value: 'objective' },
      { label: '存档', value: 'save' },
      { label: '设置', value: 'settings' },
      { label: '返回标题', value: 'title' },
    ], { x: 6, y: 30, w: 92, visible: 10, rowH: 14, padY: 4, cancelable: false });
  }
  enter(game) {
    this.game = game;
    this.c = game.campaign;
    this.ch = currentChapter(this.c);
    audio.playMusic('prep', { fade: 1 });
  }
  resume() { audio.playMusic('prep', { fade: 0.5 }); }
  units() { return this.c.available().map((id) => rosterUnit(this.c, id)); }
  deployed() { return this.c.deployList(this.ch); }

  update(game) {
    const c = this.c;
    if (game.autotest) {
      this.autoT = (this.autoT || 0) + 1;
      if (this.autoT === 40) {
        autoPrep(c, this.ch);
        game.autotestNote && game.autotestNote(`${this.ch.id} 整备完成（自动买药/分发装备/推荐加点），出击 ${this.deployed().length} 人，剩余 ${c.gold} 金`);
        c.stage = 'battle';
        autosave(game);
        game.transition(() => startBattle(game));
      }
      return;
    }
    const r = this.menu.update(game.input);
    if (!r || r.type !== 'select') return;
    switch (r.item.value) {
      case 'go':
        game.push(new ConfirmDialog(`带领 ${this.deployed().length} 人出击？`, (yes) => {
          if (!yes) return;
          c.stage = 'battle';
          autosave(game);
          game.transition(() => startBattle(game));
        }));
        break;
      case 'deploy': game.push(new DeployScene(c, this.ch)); break;
      case 'formation': game.push(new FormationScene(c, this.ch)); break;
      case 'items': game.push(new PrepItemsScene(c)); break;
      case 'shop': game.push(new ShopScene(c, this.ch)); break;
      case 'units': {
        const list = this.units();
        game.push(new UnitInfoScene(list[0], { list, campaign: c }));
        break;
      }
      case 'objective': {
        const tmp = new BattleState(this.ch, c, { seed: 1 });
        game.push(new ObjectiveScene(tmp));
        break;
      }
      case 'save': game.push(new SaveLoadScene('save')); break;
      case 'settings': game.push(new SettingsScene()); break;
      case 'title': game.push(new ConfirmDialog('返回标题画面？未保存的进度将会丢失。', (yes) => { if (yes) toTitle(game); })); break;
      default: break;
    }
  }

  draw(ctx, game) {
    fill(ctx, 0, 0, W, H, '#0d0c16');
    for (let y = 0; y < H; y += 4) { ctx.globalAlpha = 0.08; fill(ctx, 0, y, W, 1, '#8090c0'); }
    ctx.globalAlpha = 1;
    drawWindow(ctx, 4, 4, W - 8, 22, 'gold');
    drawText(ctx, `整备　${this.ch.title} ${this.ch.name}`, 12, 9, '#fff4d8', { shadow: '#2a1804' });
    drawText(ctx, `${this.c.gold} 金`, W - 12, 9, '#f8e080', { align: 'right', shadow: '#2a1804' });
    this.menu.draw(ctx, game.frame);
    // 右侧：目标与队伍
    drawWindow(ctx, 102, 30, W - 106, 44, 'dark');
    wrapText('胜利：' + this.ch.objective.text, W - 124).slice(0, 2).forEach((l, i) => drawText(ctx, l, 110, 34 + i * 13, '#f8e0a0', { shadow: '#000' }));
    drawText(ctx, '失败：' + this.ch.objective.lose, 110, 60, '#ffb0a0', { shadow: '#000' });
    const list = this.units();
    const dep = this.deployed();
    drawWindow(ctx, 102, 78, W - 106, 98, 'menu');
    drawText(ctx, `出击 ${dep.length}/${this.ch.deploy.length}`, 110, 82, '#c8d8ff', { shadow: '#000' });
    list.forEach((u, i) => {
      const col = i % 4, row = Math.floor(i / 4);
      const x = 108 + col * 52, y = 96 + row * 40;
      const on = dep.includes(u.id);
      ctx.globalAlpha = on ? 1 : 0.45;
      drawMini(ctx, u.portrait, x + 8, y);
      ctx.globalAlpha = 1;
      drawText(ctx, u.name, x + 24, y + 33 - 8, on ? '#ffffff' : '#8a88a0', { align: 'center', shadow: '#000' });
      drawText(ctx, `${u.lv}`, x + 42, y, '#f8e080', { shadow: '#000' });
      if (u.points) drawText(ctx, '★', x + 6, y, '#f8d040', { shadow: '#000' });
    });
  }
}

// 选择出击人员
class DeployScene {
  constructor(c, ch) {
    this.overlay = true;
    this.c = c; this.ch = ch;
    this.sel = c.deployList(ch);
    const ids = c.available();
    this.menu = new ListMenu(ids.map((id) => ({ label: CHARACTERS[id].name, value: id })), {
      x: 60, y: 20, w: 200, visible: Math.min(9, ids.length), rowH: 15, title: `选择出击人员（最多 ${ch.deploy.length} 人）`,
      drawItem: (ctx, it, x, y) => {
        const u = c.roster[it.value];
        const on = this.sel.includes(it.value);
        drawText(ctx, on ? '●' : '○', x, y, on ? '#80ff80' : '#8a88a0', { shadow: '#000' });
        drawText(ctx, u.name, x + 16, y, '#ffffff', { shadow: '#000' });
        drawText(ctx, CLASSES[u.cls].name, x + 64, y, '#c8d8ff', { shadow: '#000' });
        drawText(ctx, `Lv${u.lv}`, x + 150, y, '#f8e080', { shadow: '#000' });
        if (it.value === 'elwin') drawText(ctx, '必须', x + 176, y, '#f8d040', { shadow: '#000' });
      },
    });
  }
  update(game) {
    const r = this.menu.update(game.input);
    if (!r) return;
    if (r.type === 'cancel') {
      this.c.formation[this.ch.id] = this.sel.slice();
      if (this.c.formationSlots) delete this.c.formationSlots[this.ch.id];
      game.remove(this);
      return;
    }
    if (r.type !== 'select') return;
    const id = r.item.value;
    if (id === 'elwin') { audio.sfx('error'); game.showToast('王子必须出击'); return; }
    const i = this.sel.indexOf(id);
    if (i >= 0) this.sel.splice(i, 1);
    else if (this.sel.length < this.ch.deploy.length) this.sel.push(id);
    else { audio.sfx('error'); game.showToast('出击人数已满'); return; }
    this.c.formation[this.ch.id] = this.sel.slice();
  }
  draw(ctx, game) {
    ctx.globalAlpha = 0.88; fill(ctx, 0, 0, W, H, '#07060c'); ctx.globalAlpha = 1;
    this.menu.draw(ctx, game.frame);
    drawText(ctx, `已选 ${this.sel.length}/${this.ch.deploy.length}　Z 切换　X 完成`, W / 2, H - 16, '#c8d0f0', { align: 'center', shadow: '#000' });
  }
}

// 调整站位：在地图上交换出击位置
class FormationScene {
  constructor(c, ch) {
    this.c = c; this.ch = ch;
    this.state = new BattleState(ch, c, { seed: 7 });
    this.view = new MapView(this.state);
    const lord = this.state.lord();
    this.view.cursor = { x: lord.x, y: lord.y };
    this.view.centerOn(lord.x, lord.y, true);
    this.view.overlays.deploy = ch.deploy.map(([x, y]) => ({ x, y }));
    this.pick = null;
  }
  update(game) {
    const input = game.input;
    const v = this.view;
    v.update();
    const d = input.dir();
    if (d) {
      const nx = v.cursor.x + (d === 'left' ? -1 : d === 'right' ? 1 : 0), ny = v.cursor.y + (d === 'up' ? -1 : d === 'down' ? 1 : 0);
      if (this.state.inBounds(nx, ny)) { v.cursor = { x: nx, y: ny }; v.follow(nx, ny); audio.sfx('cursor', { vol: 0.4 }); }
    }
    if (input.mouse.moved && input.mouse.inside) { const t = v.tileAt(input.mouse.x, input.mouse.y); if (this.state.inBounds(t.x, t.y)) { v.cursor = t; v.follow(t.x, t.y); } }
    if (input.cancel()) {
      if (this.pick) { this.pick = null; audio.sfx('cancel'); return; }
      this.save();
      audio.sfx('cancel');
      game.pop();
      return;
    }
    if (input.confirm() || input.click()) {
      const c = v.cursor;
      const slot = this.ch.deploy.findIndex(([x, y]) => x === c.x && y === c.y);
      if (slot < 0) { audio.sfx('error'); return; }
      if (!this.pick) {
        if (!this.state.unitAt(c.x, c.y) || this.state.unitAt(c.x, c.y).team !== 'player') { audio.sfx('error'); return; }
        this.pick = { x: c.x, y: c.y };
        audio.sfx('select');
        return;
      }
      const a = this.state.unitAt(this.pick.x, this.pick.y);
      const b = this.state.unitAt(c.x, c.y);
      if (b && b.team !== 'player') { audio.sfx('error'); return; }
      this.state.setPos(a, c.x, c.y);
      if (b) this.state.setPos(b, this.pick.x, this.pick.y);
      this.pick = null;
      audio.sfx('confirm');
    }
  }
  save() {
    // 记录每个出击点上的角色（空位为 null）
    this.c.formationSlots = this.c.formationSlots || {};
    this.c.formationSlots[this.ch.id] = this.ch.deploy.map(([x, y]) => {
      const u = this.state.unitAt(x, y);
      return u && u.team === 'player' && !u.escort ? u.id : null;
    });
  }
  draw(ctx, game) {
    this.view.draw(ctx, { selected: this.pick ? this.state.unitAt(this.pick.x, this.pick.y) : null });
    drawWindow(ctx, 4, 4, W - 8, 20, 'dark', 0.92);
    drawText(ctx, this.pick ? '选择要交换到的出击位置' : '调整站位：选择一名角色，再选择另一个出击位置交换　X 完成', W / 2, 8, '#f8e0a0', { align: 'center', shadow: '#000' });
  }
}

// 物品整理：选人 → 物品菜单 / 运输队 / 交换
class PrepItemsScene {
  constructor(c) {
    this.overlay = true;
    this.c = c;
    this.build();
  }
  build(index = 0) {
    const us = this.c.available().map((id) => rosterUnit(this.c, id));
    this.us = us;
    this.menu = new ListMenu(us.map((u) => ({ label: u.name, value: u })), {
      x: 6, y: 20, w: 110, visible: Math.min(8, us.length), rowH: 16, title: '选择角色', index,
      drawItem: (ctx, it, x, y) => {
        drawText(ctx, it.value.name, x, y, '#fff', { shadow: '#000' });
        drawText(ctx, `${it.value.items.length}/${MAX_ITEMS}`, x + 84, y, '#c8d8ff', { align: 'right', shadow: '#000' });
      },
    });
    this.sub = null;
  }
  update(game) {
    if (this.sub) {
      const r = this.sub.update(game.input);
      if (!r) return;
      if (r.type === 'cancel') { this.sub = null; return; }
      const u = this.menu.current().value;
      if (r.item.value === 'items') game.push(new ItemMenuScene(u, { campaign: this.c }));
      else if (r.item.value === 'convoy') game.push(new ConvoyScene(this.c, u));
      else if (r.item.value === 'trade') {
        const others = this.us.filter((o) => o !== u);
        game.push(new PickUnitScene(others, '和谁交换？', (o) => game.push(new TradeScene(u, o))));
      }
      this.sub = null;
      return;
    }
    const r = this.menu.update(game.input);
    if (!r) return;
    if (r.type === 'cancel') { game.remove(this); return; }
    if (r.type === 'select') {
      this.sub = new ListMenu([
        { label: '物品', value: 'items' },
        { label: '运输队', value: 'convoy' },
        { label: '交换', value: 'trade', enabled: this.us.length > 1, reason: '没有其他角色' },
      ], { x: 120, y: 20 + 21 + r.index * 16, w: 70, visible: 3, rowH: 14, padY: 4 });
    }
  }
  draw(ctx, game) {
    ctx.globalAlpha = 0.88; fill(ctx, 0, 0, W, H, '#07060c'); ctx.globalAlpha = 1;
    this.menu.draw(ctx, game.frame);
    const u = this.menu.current().value;
    drawWindow(ctx, 196, 20, 120, 104, 'dark');
    drawText(ctx, u.name + ' 的物品', 204, 24, '#f8e0a0', { shadow: '#000' });
    u.items.forEach((it, i) => {
      drawIcon(ctx, ITEMS[it.id].icon, 202, 40 + i * 16);
      drawText(ctx, ITEMS[it.id].name, 220, 42 + i * 16, '#fff', { shadow: '#000' });
    });
    drawText(ctx, `运输队：${this.c.convoy.length} 件`, 204, 130, '#c8d0f0', { shadow: '#000' });
    if (this.sub) this.sub.draw(ctx, game.frame);
  }
}

class PickUnitScene {
  constructor(list, title, cb) {
    this.overlay = true;
    this.cb = cb;
    this.menu = new ListMenu(list.map((u) => ({ label: u.name, value: u })), { x: W / 2 - 50, y: 30, w: 100, visible: Math.min(8, list.length), title });
  }
  update(game) {
    const r = this.menu.update(game.input);
    if (!r) return;
    game.remove(this);
    if (r.type === 'select') this.cb(r.item.value);
  }
  draw(ctx, game) { this.menu.draw(ctx, game.frame); }
}

// 商店
class ShopScene {
  constructor(c, ch) {
    this.overlay = true;
    this.c = c; this.ch = ch;
    this.tab = 0; // 0 买 1 卖
    this.build();
  }
  priceOf(id) {
    const p = ITEMS[id].price || 0;
    return this.c.difficulty === 'easy' ? Math.round(p * 0.9) : this.c.difficulty === 'hard' ? Math.round(p * 1.1) : p;
  }
  build(index = 0) {
    const c = this.c;
    if (this.tab === 0) {
      this.menu = new ListMenu(this.ch.shop.map((id) => ({ label: ITEMS[id].name, value: id, enabled: this.priceOf(id) <= c.gold, reason: '金钱不足' })), {
        x: 6, y: 26, w: 170, visible: 8, rowH: 16, title: '购买', index,
        drawItem: (ctx, it, x, y) => {
          drawIcon(ctx, ITEMS[it.value].icon, x - 2, y - 2);
          drawText(ctx, it.label, x + 16, y, it.enabled === false ? '#8a88a0' : '#fff', { shadow: '#000' });
          drawText(ctx, String(this.priceOf(it.value)), x + 146, y, '#f8e080', { align: 'right', shadow: '#000' });
        },
      });
    } else {
      const entries = [];
      c.convoy.forEach((it, i) => entries.push({ owner: null, idx: i, it }));
      for (const id of c.available()) c.roster[id].items.forEach((it, i) => { if (!ITEMS[it.id].lock) entries.push({ owner: id, idx: i, it }); });
      this.entries = entries;
      this.menu = new ListMenu(entries.map((e, i) => ({ label: ITEMS[e.it.id].name, value: i })), {
        x: 6, y: 26, w: 190, visible: 8, rowH: 16, title: '出售（半价）', index: Math.min(index, Math.max(0, entries.length - 1)),
        drawItem: (ctx, it, x, y) => {
          const e = entries[it.value];
          drawIcon(ctx, ITEMS[e.it.id].icon, x - 2, y - 2);
          drawText(ctx, ITEMS[e.it.id].name, x + 16, y, '#fff', { shadow: '#000' });
          drawText(ctx, e.owner ? CHARACTERS[e.owner].name : '仓库', x + 100, y, '#c8d8ff', { shadow: '#000' });
          drawText(ctx, String(this.sellPrice(e.it)), x + 166, y, '#f8e080', { align: 'right', shadow: '#000' });
        },
      });
    }
  }
  sellPrice(it) {
    const d = ITEMS[it.id];
    const base = Math.floor((d.price || 0) / 2);
    if (d.uses && d.type === 'item') return Math.floor((base * it.uses) / d.uses);
    return base;
  }
  update(game) {
    const input = game.input;
    if (input.pressed('left') || input.pressed('right')) { this.tab = 1 - this.tab; this.build(); audio.sfx('page'); return; }
    const r = this.menu.update(input);
    if (!r) return;
    if (r.type === 'cancel') { game.remove(this); return; }
    if (r.type === 'blocked') { game.showToast(r.item.reason); return; }
    if (r.type !== 'select') return;
    const c = this.c;
    if (this.tab === 0) {
      const id = r.item.value;
      const price = this.priceOf(id);
      const opts = [{ label: '放入运输队', value: null }].concat(c.available().map((uid) => ({ label: `交给 ${CHARACTERS[uid].name}`, value: uid, enabled: c.roster[uid].items.length < MAX_ITEMS, reason: '物品已满' })));
      game.push(new PickListScene(opts, `购买 ${ITEMS[id].name}（${price} 金）`, (who) => {
        if (c.gold < price) { audio.sfx('error'); return; }
        c.gold -= price;
        const item = makeItem(id);
        if (who) c.roster[who].items.push(item); else c.convoy.push(item);
        audio.sfx('gold');
        game.showToast(`购买了 ${ITEMS[id].name}`);
        this.build(this.menu.index);
      }));
    } else {
      const e = this.entries[r.item.value];
      const price = this.sellPrice(e.it);
      game.push(new ConfirmDialog(`以 ${price} 金出售 ${ITEMS[e.it.id].name}？`, (yes) => {
        if (!yes) return;
        if (e.owner) {
          const u = c.roster[e.owner];
          u.items.splice(e.idx, 1);
          if (u.equip != null && u.equip >= e.idx) u.equip = u.equip === e.idx ? null : u.equip - 1;
        } else c.convoy.splice(e.idx, 1);
        c.gold += price;
        audio.sfx('gold');
        this.build(this.menu.index);
      }));
    }
  }
  draw(ctx, game) {
    fill(ctx, 0, 0, W, H, '#0d0c16');
    drawWindow(ctx, 4, 4, W - 8, 20, 'gold');
    drawText(ctx, `商店　${this.tab === 0 ? '【购买】 出售' : '购买 【出售】'}　←→ 切换`, 12, 8, '#fff4d8', { shadow: '#2a1804' });
    drawText(ctx, `${this.c.gold} 金`, W - 12, 8, '#f8e080', { align: 'right', shadow: '#2a1804' });
    this.menu.draw(ctx, game.frame);
    if (this.tab === 1 && !this.entries.length) drawText(ctx, '（没有可出售的物品）', 40, 52, '#8a88a0', { shadow: '#000' });
    const it = this.menu.current();
    if (!it) return;
    const id = this.tab === 0 ? it.value : this.entries[it.value].it.id;
    const d = ITEMS[id];
    drawWindow(ctx, 200, 26, W - 204, 150, 'dark');
    drawText(ctx, d.name, 208, 30, '#f8e0a0', { shadow: '#000' });
    const lines = [];
    if (d.mt != null) lines.push(`威力 ${d.mt}  命中 ${d.hit}`);
    if (d.crit != null) lines.push(`必杀 ${d.crit}  重量 ${d.wt}`);
    if (d.rng && d.type !== 'item') lines.push(`射程 ${d.rng[0]}~${d.rng[1] === 'mag' ? '魔力÷2' : d.rng[1]}`);
    lines.push(...wrapText(d.desc, W - 220));
    const who = c2users(this.c, d);
    if (who) lines.push(...wrapText('可用：' + who, W - 220));
    lines.slice(0, 9).forEach((l, i) => drawText(ctx, l, 208, 46 + i * 13, '#e8e4d8', { shadow: '#000' }));
  }
}

function c2users(c, d) {
  if (d.type === 'item') return '';
  const names = c.available().filter((id) => {
    const u = c.roster[id];
    if (d.lock && d.lock !== id) return false;
    return CLASSES[u.cls].weapons.includes(d.type);
  }).map((id) => CHARACTERS[id].name);
  return names.join('、') || '（队伍中无人可用）';
}

class PickListScene {
  constructor(items, title, cb) {
    this.overlay = true;
    this.cb = cb;
    this.menu = new ListMenu(items, { x: W / 2 - 70, y: 30, w: 140, visible: Math.min(9, items.length), rowH: 14, title });
  }
  update(game) {
    const r = this.menu.update(game.input);
    if (!r) return;
    if (r.type === 'blocked') { game.showToast(r.item.reason); return; }
    game.remove(this);
    if (r.type === 'select') this.cb(r.item.value);
  }
  draw(ctx, game) { this.menu.draw(ctx, game.frame); }
}
