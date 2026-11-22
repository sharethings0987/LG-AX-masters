/* 인생그램 ↔ 백엔드 연동 (v8 A·B·C 공용)
 * 각 HTML의 게임 스크립트 다음에 로드되며 POL, PK, SITE, JB, CARE, VARI, G, S, draw, tst, rd 를 그대로 사용한다.
 * 서버에 연결되지 않으면 아무것도 바꾸지 않는다: 게임은 HTML 안의 내장 정책과 localStorage로 지금처럼 동작한다.
 */
const BE = (() => {
  // 서버(uvicorn)가 이 페이지를 직접 서빙하면 같은 출처, HTML을 파일로 열었으면 로컬 서버를 찾는다.
  const API = (window.AL_API_BASE_URL || (location.protocol.startsWith('http') ? '' : 'http://127.0.0.1:8000'))
    .replace(/\/+$/, '');
  const newId = () => (self.crypto && crypto.randomUUID) ? crypto.randomUUID()
    : 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  const PID = (() => {
    try {
      let p = localStorage.getItem('al_pid');
      if (!/^[A-Za-z0-9_-]{8,64}$/.test(p || '')) { p = newId(); localStorage.setItem('al_pid', p); }
      return p;
    } catch (e) { return newId(); } // 저장이 막힌 환경: 이번 접속에서만 쓰는 ID
  })();

  const req = (path, o = {}) => fetch(API + path, { ...o, headers: { 'Content-Type': 'application/json' } })
    .then(r => { if (!r.ok) throw new Error(`${path} → ${r.status}`); return r.json(); });

  /* ---------- 정책 규칙 → 판정 함수 (backend/app/schemas.py 의 Rule 과 짝) ---------- */
  const DERIVED = { employed: g => JB[g.job].e == 1, tenure: g => g.m - g.hm };
  const val = (g, f) => DERIVED[f] ? DERIVED[f](g) : f.split('.').reduce((o, k) => o == null ? undefined : o[k], g);
  const OPS = {
    between: (x, v) => x >= v[0] && x <= v[1], in: (x, v) => v.includes(x),
    lt: (x, v) => x < v, le: (x, v) => x <= v, gt: (x, v) => x > v, ge: (x, v) => x >= v,
    eq: (x, v) => x === v, truthy: x => !!x,
  };
  const compile = r => {
    if (r.all) { const a = r.all.map(compile); return g => a.every(f => f(g)); }
    if (r.any) { const a = r.any.map(compile); return g => a.some(f => f(g)); }
    const op = OPS[r.op];
    if (!op) throw new Error('알 수 없는 op: ' + r.op);
    return g => op(val(g, r.field), r.value);
  };

  let online = false;
  function loadPolicies() {
    return req('/api/policies').then(d => {
      const sites = { ...SITE, ...d.sites }, next = {};
      for (const p of d.policies) {
        if (!sites[p.site]) { console.warn('[인생그램] 사이트 정보가 없어 건너뜀:', p.key); continue; }
        const P = { n: p.name, w: p.site, h: p.hint, d: p.description, fx: p.effects,
                    req: p.requirements.map(r => [r.label, compile(r)]) };
        P.ok = g => P.req.every(r => r[1](g));
        next[p.key] = P;
      }
      if (!Object.keys(next).length) return;
      Object.assign(SITE, sites);
      // 서버에서 빠진(비활성) 정책도 POL에는 남겨 두어 진행 중인 이벤트 문구가 깨지지 않게 하고,
      // PK(게임이 실제로 등장시키는 목록)에서만 뺀다.
      Object.assign(POL, next);
      PK.splice(0, PK.length, ...Object.keys(next));
      online = true;
      console.info(`[인생그램] 서버 정책 ${PK.length}개를 불러왔습니다.`);
    }).catch(e => console.info('[인생그램] 서버에 연결하지 못해 내장 정책을 씁니다.', e.message));
  }

  /* ---------- 편지 ---------- */
  let letters = null;
  function syncLetters() {
    return req('/api/letters?player_id=' + encodeURIComponent(PID)).then(d => {
      letters = d.map(l => ({ to: l.to, text: l.text, date: new Date(l.created_at).toLocaleDateString('ko-KR') }));
      if (S == 'start') draw();
    }).catch(() => {});
  }
  function saveLetter(to, text, localOk) {
    req('/api/letters', { method: 'POST', body: JSON.stringify({ player_id: PID, to, text, play_id: (G && G.playId) || null }) })
      .then(() => { tst('💌 편지를 저장했어요. 처음 화면의 편지함에서 볼 수 있어요'); syncLetters(); })
      .catch(() => tst(localOk ? '💌 이 기기에 편지를 저장했어요 (서버에는 연결되지 않았어요)'
                               : '이 환경에서는 저장되지 않아요. 복사해서 보관해주세요'));
  }

  /* ---------- 플레이 기록 ---------- */
  function savePlay() {
    const g = G;
    if (!g || g.playP) return;
    const m = g.me, stats = {};
    for (const k in g.st) stats[k] = rd(g.st[k]);
    const body = {
      player_id: PID, variant: VARI, mode: g.mode, auto: !!g.auto,
      care: g.care ? (Object.keys(CARE).find(k => CARE[k] === g.care) || null) : null,
      character: { name: m.n, region: m.rg, family: m.q, path: m.path },
      result: { job: g.job, house: g.h, stats, cash: rd(g.cash), debt: rd(g.debt),
                partner: !!g.f.partner, married: !!g.f.married, kid: !!g.f.kid, pet: !!g.f.pet },
      eligible: Object.keys(g.elig), done: Object.keys(g.done), missed: Object.keys(g.miss), heard: Object.keys(g.heard),
      year_map: g.map.map(c => ({ age: c.age, mood: Math.round(c.mood * 10) / 10, text: String(c.t).slice(0, 300) })),
    };
    g.playP = req('/api/plays', { method: 'POST', body: JSON.stringify(body) }).then(d => (g.playId = d.id));
    g.playP.catch(e => console.info('[인생그램] 플레이 기록을 저장하지 못했습니다.', e.message));
  }
  function patchPlay() {
    const g = G;
    if (!g || !g.playP) return;
    const body = { player_id: PID };
    if (g.ans) body.goal_answer = g.ans;
    if (g.thx) body.thanks_answer = g.thx;
    g.playP.then(id => req('/api/plays/' + id, { method: 'PATCH', body: JSON.stringify(body) })).catch(() => {});
  }

  loadPolicies();
  syncLetters();
  return {
    pid: PID,
    get online() { return online; },
    letters: () => (letters && letters.length ? letters : null),
    saveLetter, savePlay, patchPlay, loadPolicies, compile,
  };
})();
