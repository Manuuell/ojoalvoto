'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';

pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`;

const FIELDS = [
  ['votantes_e11', 'Total votantes E-11', 'Nivelación de la mesa'],
  ['votos_urna', 'Total votos en la urna', 'Nivelación de la mesa'],
  ['incinerados', 'Votos incinerados', 'Nivelación de la mesa'],
  ['cepeda', '1. Iván Cepeda', 'Candidatos · Página 1'],
  ['claudia', '2. Claudia López', 'Candidatos · Página 1'],
  ['botero', '3. Botero Jaramillo', 'Candidatos · Página 1'],
  ['espriella', '4. De la Espriella', 'Candidatos · Página 1'],
  ['lizcano', '5. Lizcano Arango', 'Candidatos · Página 1'],
  ['uribe', '6. Uribe Londoño', 'Candidatos · Página 1'],
  ['sondra', '7. Sondra Garvin', 'Candidatos · Página 1'],
  ['barreras', '8. Barreras', 'Candidatos · Página 2'],
  ['caicedo', '9. Caicedo Omar', 'Candidatos · Página 2'],
  ['matamoros', '10. Matamoros', 'Candidatos · Página 2'],
  ['paloma', '11. Paloma Valencia', 'Candidatos · Página 2'],
  ['fajardo', '12. Fajardo', 'Candidatos · Página 2'],
  ['murillo', '13. Murillo Urrutia', 'Candidatos · Página 2'],
  ['blanco', 'Votos en blanco', 'Otros'],
  ['nulo', 'Votos nulos', 'Otros'],
  ['no_marcadas', 'Tarjetas no marcadas', 'Otros'],
  ['suma_total', 'SUMA TOTAL', 'Otros'],
] as const;
const CANDS = ['cepeda','claudia','botero','espriella','lizcano','uribe','sondra','barreras','caicedo','matamoros','paloma','fajardo','murillo'];
const DEFMAP: Record<string, { p: number; x: number; y: number }> = {"votantes_e11":{"p":0,"x":0.814,"y":0.259},"votos_urna":{"p":0,"x":0.835,"y":0.288},"incinerados":{"p":0,"x":0.814,"y":0.314},"cepeda":{"p":0,"x":0.824,"y":0.407},"claudia":{"p":0,"x":0.808,"y":0.492},"botero":{"p":0,"x":0.792,"y":0.577},"espriella":{"p":0,"x":0.792,"y":0.665},"lizcano":{"p":0,"x":0.781,"y":0.749},"uribe":{"p":0,"x":0.781,"y":0.839},"sondra":{"p":0,"x":0.781,"y":0.92},"barreras":{"p":1,"x":0.786,"y":0.289},"caicedo":{"p":1,"x":0.791,"y":0.379},"matamoros":{"p":1,"x":0.786,"y":0.464},"paloma":{"p":1,"x":0.791,"y":0.55},"fajardo":{"p":1,"x":0.791,"y":0.638},"murillo":{"p":1,"x":0.791,"y":0.718},"blanco":{"p":1,"x":0.796,"y":0.786},"nulo":{"p":1,"x":0.828,"y":0.811},"no_marcadas":{"p":1,"x":0.823,"y":0.838},"suma_total":{"p":1,"x":0.817,"y":0.867}};
const fmt = (n: number) => Number(n || 0).toLocaleString('es-CO');

export default function App() {
  const [view, setView] = useState('home');               // home | verify | board | fraude | stats
  const [labeler, setLabeler] = useState('');
  const labelerRef = useRef('');
  const [acta, setActa] = useState<any>(null);
  const [page, setPage] = useState(0);
  const [vals, setVals] = useState<Record<string, string>>({});
  const [stats, setStats] = useState<any>(null);
  const [board, setBoard] = useState<any[]>([]);
  const [fraude, setFraude] = useState<any[]>([]);
  const [elec, setElec] = useState<any>(null);
  const [dims, setDims] = useState({ w: 0, h: 0 });
  const view2 = useRef<HTMLDivElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const t = useRef({ scale: 1, tx: 0, ty: 0, fit: 1 });
  const pendingFocus = useRef<{ x: number; y: number } | null>(null);
  const mapRef = useRef<any>(JSON.parse(JSON.stringify(DEFMAP)));
  const focused = useRef('votantes_e11');
  const [calibrating, setCalibrating] = useState(false);
  const pdfUrl = acta ? `/api/actas/${acta.acta_id}/pdf` : null;

  useEffect(() => { try { const s = localStorage.getItem('e14map_v2'); if (s) mapRef.current = JSON.parse(s); } catch {} }, []);
  useEffect(() => {
    const s = localStorage.getItem('ovlabeler'); if (s) { setLabeler(s); labelerRef.current = s; }
    const load = () => fetch('/api/stats').then((r) => r.json()).then(setStats).catch(() => {});
    load(); const id = setInterval(load, 15000); return () => clearInterval(id);
  }, []);
  useEffect(() => {
    if (view === 'board') fetch('/api/leaderboard').then(r => r.json()).then(setBoard).catch(() => {});
    if (view === 'fraude') fetch('/api/flagged').then(r => r.json()).then(setFraude).catch(() => {});
    if (view === 'stats') fetch('/api/elecciones').then(r => r.json()).then(setElec).catch(() => {});
  }, [view]);

  // ---------- Zoom ----------
  const applyT = () => { if (wrap.current) wrap.current.style.transform = `translate(${t.current.tx}px,${t.current.ty}px) scale(${t.current.scale})`; };
  const fit = () => { if (!view2.current || !dims.w) return; const c = view2.current; const f = Math.min(c.clientWidth / dims.w, c.clientHeight / dims.h) * 0.96; t.current = { ...t.current, scale: f, fit: f, tx: (c.clientWidth - dims.w * f) / 2, ty: (c.clientHeight - dims.h * f) / 2 }; applyT(); };
  const focusCell = (fx: number, fy: number, vf = 0.17) => { if (!view2.current || !dims.w) return; const c = view2.current; const s = Math.min(c.clientHeight / (vf * dims.h), 14); t.current = { ...t.current, scale: s, tx: c.clientWidth / 2 - fx * dims.w * s, ty: c.clientHeight / 2 - fy * dims.h * s }; applyT(); };
  const focusField = (f: string) => { const m = mapRef.current[f]; if (!m) return; if (m.p !== page) { pendingFocus.current = { x: m.x, y: m.y }; setPage(m.p); } else if (dims.w) focusCell(m.x, m.y); else pendingFocus.current = { x: m.x, y: m.y }; };
  const onPageRender = (pg: any) => { const vp = pg.getViewport ? pg.getViewport({ scale: 1.5 }) : { width: pg.width, height: pg.height }; setDims({ w: vp.width, h: vp.height }); };
  useEffect(() => { if (!dims.w) return; if (pendingFocus.current) { focusCell(pendingFocus.current.x, pendingFocus.current.y); pendingFocus.current = null; } else fit(); /* eslint-disable-next-line */ }, [dims, page]);

  // ---------- Flujo ----------
  const loadNext = useCallback(async () => {
    const who = labelerRef.current || labeler;
    const d = await (await fetch(`/api/actas/next?labeler=${encodeURIComponent(who)}`)).json();
    if (d.done) { alert('¡No quedan actas pendientes! Gracias por ayudar 🎉'); return; }
    setActa(d); const pf = d.prefill?.votes || d.prefill || {}; const init: Record<string, string> = {};
    FIELDS.forEach(([k]) => (init[k] = pf[k] != null ? String(pf[k]) : '')); setVals(init);
    pendingFocus.current = mapRef.current.votantes_e11; setPage(0);
    setTimeout(() => document.getElementById('f_votantes_e11')?.focus(), 60);
  }, [labeler]);
  const refreshStats = () => fetch('/api/stats').then(r => r.json()).then(setStats).catch(() => {});
  const goVerify = () => {
    let n = labelerRef.current || labeler;
    if (!n) { n = (window.prompt('Escribe tu nombre o apodo para empezar a verificar:') || '').trim(); if (!n) return; setLabeler(n); labelerRef.current = n; localStorage.setItem('ovlabeler', n); }
    setView('verify'); loadNext(); refreshStats();
  };

  const num = (k: string) => parseInt(vals[k] || '0') || 0;
  const sumVotos = CANDS.reduce((a, k) => a + num(k), 0) + num('blanco') + num('nulo') + num('no_marcadas');
  const urna = num('votos_urna'), e11 = num('votantes_e11');
  let checkOk = false, checkMsg = 'Ingresa los votos…', checkKind = 'neutral';
  if (urna > 0 && e11 > 0 && urna > e11) { checkKind = 'fraud'; checkMsg = `Posible fraude — urna (${urna}) supera votantes (${e11})`; }
  else if (e11 > 0 && sumVotos > e11) { checkKind = 'fraud'; checkMsg = `Posible fraude — votos (${sumVotos}) superan votantes (${e11})`; }
  else { const tg = urna || e11; const st = num('suma_total'); const extra = st > 0 && st !== sumVotos ? ` · el jurado anotó ${st}` : '';
    if (tg > 0 && sumVotos === tg) { checkKind = 'ok'; checkMsg = `Cuadra: ${sumVotos} votos = urna${extra}`; checkOk = true; }
    else if (tg > 0) { checkKind = 'bad'; checkMsg = `No cuadra: ${sumVotos} ≠ urna ${tg} (dif ${sumVotos - tg})`; }
    else checkMsg = `Suma de votos: ${sumVotos}`; }

  const votesObj = () => { const o: any = {}; FIELDS.forEach(([k]) => (o[k] = num(k))); return o; };
  const post = (p: string, b: any) => fetch(`/api/actas/${acta.acta_id}/${p}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) });
  const submit = async () => { if (!acta) return; await post('submit', { labeler: labelerRef.current, votes: votesObj() }); loadNext(); refreshStats(); };
  const flag = async () => { if (!acta) return; const nota = prompt('¿Por qué es sospechosa? (opcional)') || ''; await post('flag', { labeler: labelerRef.current, votes: votesObj(), nota }); loadNext(); refreshStats(); };
  const skip = async () => { if (!acta) return; await post('skip', {}); loadNext(); refreshStats(); };

  const drag = useRef({ on: false, moved: false, x: 0, y: 0, dx: 0, dy: 0 });
  const onWheel = (e: React.WheelEvent) => { e.preventDefault(); const c = view2.current!; const r = c.getBoundingClientRect(); const ns = Math.min(Math.max(t.current.scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15), t.current.fit * 0.5), 14); const mx = e.clientX - r.left, my = e.clientY - r.top; t.current.tx = mx - (mx - t.current.tx) * (ns / t.current.scale); t.current.ty = my - (my - t.current.ty) * (ns / t.current.scale); t.current.scale = ns; applyT(); };
  const toggleCalib = () => { const on = !calibrating; setCalibrating(on); if (on) { setPage(0); setTimeout(() => { document.getElementById('f_votantes_e11')?.focus(); fit(); }, 80); } else localStorage.setItem('e14map_v2', JSON.stringify(mapRef.current)); };
  const onCanvasUp = (e: React.MouseEvent) => { const wasDrag = drag.current.moved; drag.current.on = false; if (!calibrating || wasDrag || !dims.w) return; const c = view2.current!; const r = c.getBoundingClientRect(); const fx = ((e.clientX - r.left) - t.current.tx) / (dims.w * t.current.scale); const fy = ((e.clientY - r.top) - t.current.ty) / (dims.h * t.current.scale); mapRef.current[focused.current] = { p: page, x: +fx.toFixed(3), y: +fy.toFixed(3) }; localStorage.setItem('e14map_v2', JSON.stringify(mapRef.current)); const idx = FIELDS.findIndex((f) => f[0] === focused.current); const nx = FIELDS[idx + 1]; if (nx) document.getElementById('f_' + nx[0])?.focus(); else { setCalibrating(false); window.prompt('Calibración lista ✓ — copia este MAP:', JSON.stringify(mapRef.current)); } };

  // ===================== NAVBAR =====================
  const Nav = () => (
    <nav style={S.nav}>
      <div onClick={() => setView('home')} style={S.brandBtn}><span style={{ fontSize: 22 }}>👁️</span><span style={S.brandName}>Ojo al Voto</span></div>
      <div style={S.navLinks}>
        {[['home','Inicio'],['board','Tablero'],['fraude','Posible fraude'],['stats','Estadísticas']].map(([v,l]) => (
          <button key={v} onClick={() => setView(v)} style={{ ...S.navLink, ...(view === v ? S.navLinkActive : {}) }}>{l}</button>
        ))}
      </div>
      <div style={{ flex: 1 }} />
      <button onClick={goVerify} style={S.navCta}>Verificar actas →</button>
    </nav>
  );

  // ===================== VERIFY (etiquetado) =====================
  if (view === 'verify') {
    const pct = stats ? ((stats.done / stats.total) * 100).toFixed(2) : '0';
    return (
      <div style={S.app}>
        <header style={S.vHeader}>
          <button onClick={() => setView('home')} style={S.backBtn}>← Inicio</button>
          <div style={S.brandBtn}><span style={{ fontSize: 18 }}>👁️</span><span style={S.brandNameSm}>Ojo al Voto</span></div>
          <div style={S.progWrap}><div style={S.progTrack}><div style={{ ...S.progFill, width: `${pct}%` }} /></div><span style={S.progTxt}>{stats ? `${fmt(stats.done)} / ${fmt(stats.total)}` : '…'}</span></div>
          <div style={{ flex: 1 }} />
          <button onClick={toggleCalib} style={{ ...S.statBtn, ...(calibrating ? { background: '#b45309', color: '#fff', borderColor: '#b45309' } : {}) }}>{calibrating ? 'Calibrando…' : '🎯 Calibrar'}</button>
          <span style={S.userChip}>👤 {labeler}</span>
        </header>
        <main style={S.main}>
          <section style={S.viewerCol}>
            <div style={S.tabs}>
              {[0, 1].map((p) => (<button key={p} onClick={() => setPage(p)} style={{ ...S.tab, ...(page === p ? S.tabActive : {}) }}>Página {p + 1} · {p === 0 ? 'candidatos 1–7' : 'candidatos 8–13 + totales'}</button>))}
              <div style={{ flex: 1 }} />
              <span style={S.viewerHint}>{calibrating ? '🎯 Clic en la casilla del campo enfocado' : 'Rueda: zoom · Arrastra: mover · Doble clic: ajustar'}</span>
            </div>
            <div ref={view2} onWheel={onWheel} onMouseDown={(e) => { drag.current = { on: true, moved: false, x: e.clientX - t.current.tx, y: e.clientY - t.current.ty, dx: e.clientX, dy: e.clientY }; }} onMouseMove={(e) => { if (!drag.current.on) return; if (Math.abs(e.clientX - drag.current.dx) > 4 || Math.abs(e.clientY - drag.current.dy) > 4) drag.current.moved = true; t.current.tx = e.clientX - drag.current.x; t.current.ty = e.clientY - drag.current.y; applyT(); }} onMouseUp={onCanvasUp} onDoubleClick={fit} style={{ ...S.canvas, cursor: calibrating ? 'crosshair' : 'grab' }}>
              <div ref={wrap} style={{ position: 'absolute', top: 0, left: 0, transformOrigin: '0 0' }}>
                {pdfUrl && <Document file={pdfUrl} loading={<div style={S.loading}>Cargando acta…</div>} error={<div style={S.loading}>No se pudo cargar el PDF</div>}><Page pageNumber={page + 1} scale={1.5} renderTextLayer={false} renderAnnotationLayer={false} onRenderSuccess={onPageRender} /></Document>}
              </div>
              <div style={S.zoomCtl}><button style={S.zoomBtn} onClick={() => { t.current.scale = Math.min(t.current.scale * 1.3, 14); applyT(); }}>+</button><button style={S.zoomBtn} onClick={() => { t.current.scale = Math.max(t.current.scale / 1.3, t.current.fit * 0.5); applyT(); }}>−</button><button style={S.zoomBtn} onClick={fit}>⤢</button></div>
            </div>
          </section>
          <aside style={S.panel}>
            <div style={S.panelHead}><div style={S.actaId}>{acta?.acta_id || '—'}</div><div style={S.actaInfo}>{acta && `${acta.info.dept} · Mun. ${acta.info.mun} · Zona ${acta.info.zona} · Puesto ${acta.info.stand} · Mesa ${acta.info.mesa}`}</div></div>
            <div style={S.fields}>
              {FIELDS.map(([k, label, grp], i) => { const prev = i > 0 ? FIELDS[i - 1][2] : null;
                return (<div key={k}>{grp !== prev && <div style={S.section}>{grp}</div>}
                  <div style={S.fieldRow}><label style={{ ...S.fieldLabel, ...(k === 'suma_total' ? { fontWeight: 700 } : {}) }}>{label}</label>
                    <input id={`f_${k}`} inputMode="numeric" value={vals[k] || ''} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} onFocus={(e) => { focused.current = k; e.target.closest('div')?.scrollIntoView({ block: 'center', behavior: 'smooth' }); if (calibrating) { const m = mapRef.current[k]; if (m.p !== page) setPage(m.p); setTimeout(fit, 60); } else focusField(k); }} onKeyDown={(e) => { if (e.key !== 'Enter') return; e.preventDefault(); if (e.ctrlKey) { submit(); return; } const nx = document.getElementById(`f_${FIELDS[i + 1]?.[0]}`); if (nx) (nx as HTMLInputElement).focus(); else if (checkOk) submit(); }} style={S.fieldInput} />
                  </div></div>); })}
            </div>
            <div style={S.panelFoot}>
              <div style={{ ...S.status, ...S[checkKind] }}><span>{checkKind === 'ok' ? '✓' : checkKind === 'fraud' ? '🚩' : checkKind === 'bad' ? '✕' : '•'}</span><span>{checkMsg}</span></div>
              <button onClick={submit} style={S.btnPrimary}>Guardar y continuar</button>
              <div style={{ display: 'flex', gap: 8 }}><button onClick={flag} style={S.btnDanger}>🚩 Reportar fraude</button><button onClick={skip} style={S.btnGhost}>Ilegible</button></div>
            </div>
          </aside>
        </main>
      </div>
    );
  }

  // ===================== SITIO PÚBLICO =====================
  const total = stats?.total || 121041, done = stats?.done || 0, fr = stats?.flagged || 0;
  const lpct = total ? ((done / total) * 100).toFixed(2) : '0';
  return (
    <div style={S.site}>
      <Nav />

      {view === 'home' && (<>
        <section style={S.hero}>
          <div style={S.flagBar} />
          <h1 style={S.heroTitle}>Cuidemos entre todos<br />las elecciones de 2026</h1>
          <p style={S.heroSub}>Ojo al Voto es una iniciativa ciudadana y abierta para revisar las <b>122.020 actas E-14</b> de Colombia, detectar inconsistencias y dar transparencia al conteo.</p>
          <div style={S.heroCta}><button onClick={goVerify} style={S.introBtn}>Empezar a verificar →</button><button onClick={() => setView('stats')} style={S.introGhost}>Ver estadísticas</button></div>
        </section>
        <section style={S.block}>
          <h2 style={S.h2}>Así va la verificación ciudadana</h2>
          <p style={S.blockSub}>Progreso en tiempo real · se actualiza solo</p>
          <div style={S.statsRow}>
            <div style={S.donutBox}><div style={{ ...S.donutL, background: `conic-gradient(#1d4ed8 ${lpct}%, #e2e8f0 0)` }}><span style={S.donutLTxt}>{lpct}%</span></div><div style={S.donutCap}>verificado</div></div>
            <div style={S.cardsGrid}>{[['Actas totales', total, '#0f172a'], ['Verificadas', Math.max(done - fr, 0), '#16a34a'], ['Pendientes', stats?.pending ?? total, '#64748b'], ['Reportes de fraude', fr, '#dc2626']].map(([l, v, c]: any) => (<div key={l} style={S.statCard}><div style={{ ...S.statVal, color: c }}>{fmt(v)}</div><div style={S.statLbl}>{l}</div></div>))}</div>
          </div>
        </section>
        <section style={S.block}>
          <h2 style={S.h2}>¿Cómo funciona?</h2>
          <div style={S.stepGrid}>{[['1','Lee el acta','El sistema acerca la imagen a cada casilla. Solo escribes el número que ves.'],['2','Se verifica','Comprobamos que los votos cuadren con el total de la urna automáticamente.'],['3','Reporta lo dudoso','Si algo es sospechoso —como más votos que votantes— lo marcas con un clic.']].map(([n,h,d]) => (<div key={n} style={S.stepCard}><div style={S.stepNum}>{n}</div><div style={S.stepH}>{h}</div><div style={S.stepD}>{d}</div></div>))}</div>
          <div style={{ textAlign: 'center', marginTop: 24 }}><button onClick={goVerify} style={S.introBtn}>Quiero ayudar →</button></div>
        </section>
        <footer style={S.footer}>Ojo al Voto · Iniciativa ciudadana abierta y sin fines de lucro · Datos públicos de la Registraduría Nacional del Estado Civil</footer>
      </>)}

      {view === 'board' && (
        <section style={S.block}>
          <h2 style={S.h2}>🏆 Tablero de colaboradores</h2>
          <p style={S.blockSub}>Quienes más actas han verificado. ¡Gracias por cuidar el voto!</p>
          <div style={S.tableWrap}>
            {board.length === 0 && <div style={S.empty}>Aún nadie ha verificado actas. ¡Sé el primero!</div>}
            {board.map((r) => (<div key={r.rank} style={{ ...S.boardRow, ...(r.rank <= 3 ? S.boardTop : {}) }}>
              <span style={S.boardRank}>{['🥇','🥈','🥉'][r.rank - 1] || r.rank}</span>
              <span style={{ flex: 1, fontWeight: 600 }}>{r.labeler}</span>
              <span style={S.boardN}>{fmt(r.n)} actas</span>
            </div>))}
          </div>
        </section>
      )}

      {view === 'fraude' && (
        <section style={S.block}>
          <h2 style={S.h2}>🚩 Actas con posible fraude</h2>
          <p style={S.blockSub}>Actas reportadas por la ciudadanía por inconsistencias. Cada una requiere revisión.</p>
          <div style={S.tableWrap}>
            {fraude.length === 0 && <div style={S.empty}>Aún no hay reportes de posible fraude.</div>}
            {fraude.map((f) => (<div key={f.acta_id} style={S.fraudeRow}>
              <div><div style={S.actaIdSm}>{f.acta_id}</div><div style={S.actaInfoSm}>Depto {f.dept} · Mun {f.mun} · Zona {f.zona} · Mesa {f.mesa}</div></div>
              <div style={{ flex: 1 }} />
              {f.data?.nota && <span style={S.nota}>“{f.data.nota}”</span>}
              <span style={S.reporter}>por {f.labeler || 'anónimo'}</span>
            </div>))}
          </div>
        </section>
      )}

      {view === 'stats' && elec && (
        <section style={S.block}>
          <h2 style={S.h2}>📊 Estadísticas de las elecciones</h2>
          <p style={S.blockSub}>{elec.oficial.fecha} · Fuente: Registraduría Nacional · cruzado con la verificación ciudadana</p>

          <div style={S.statsTopGrid}>
            <div style={S.bigCard}><div style={S.bigVal}>{fmt(elec.oficial.votantes)}</div><div style={S.bigLbl}>Votantes ({elec.oficial.participacion}% de participación)</div></div>
            <div style={S.bigCard}><div style={S.bigVal}>{fmt(elec.oficial.validos)}</div><div style={S.bigLbl}>Votos válidos</div></div>
            <div style={S.bigCard}><div style={{ ...S.bigVal, color: '#16a34a' }}>{fmt(elec.verificacion.verificadas)}</div><div style={S.bigLbl}>Actas verificadas por ciudadanos</div></div>
            <div style={S.bigCard}><div style={{ ...S.bigVal, color: '#dc2626' }}>{fmt(elec.verificacion.fraude)}</div><div style={S.bigLbl}>Reportes de posible fraude</div></div>
          </div>

          <h3 style={S.h3}>Resultados oficiales (preconteo)</h3>
          <div style={S.barsWrap}>
            {elec.oficial.candidatos.map((c: any, i: number) => (
              <div key={c.nombre} style={S.barRow}>
                <span style={S.barName}>{c.nombre}</span>
                <div style={S.barTrack}><div style={{ ...S.barFill, width: `${Math.max(c.pct, 0.4)}%`, background: i === 0 ? '#1d4ed8' : i === 1 ? '#0ea5e9' : '#94a3b8' }} /></div>
                <span style={S.barPct}>{c.pct}%</span>
                <span style={S.barVotes}>{fmt(c.votos)}</span>
              </div>
            ))}
          </div>
          <p style={S.disclaimer}>Los resultados oficiales provienen del preconteo de la Registraduría. La verificación ciudadana de Ojo al Voto contrasta esos totales con lo que dice cada acta E-14 original, para detectar diferencias.</p>
        </section>
      )}
      {view === 'stats' && !elec && <section style={S.block}><div style={S.empty}>Cargando estadísticas…</div></section>}
    </div>
  );
}

const BLUE = '#1d4ed8', INK = '#0f172a', MUTE = '#64748b', LINE = '#e2e8f0';
const S: any = {
  site: { minHeight: '100vh', background: '#fff', color: INK },
  nav: { display: 'flex', alignItems: 'center', gap: 8, padding: '12px 24px', borderBottom: `1px solid ${LINE}`, position: 'sticky', top: 0, background: 'rgba(255,255,255,.92)', backdropFilter: 'blur(8px)', zIndex: 20 },
  brandBtn: { display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' },
  brandName: { fontSize: 19, fontWeight: 800, color: INK }, brandNameSm: { fontSize: 16, fontWeight: 800, color: INK },
  navLinks: { display: 'flex', gap: 4, marginLeft: 20 },
  navLink: { padding: '8px 14px', fontSize: 14, border: 'none', background: 'none', color: MUTE, cursor: 'pointer', borderRadius: 8, fontWeight: 600 },
  navLinkActive: { color: BLUE, background: '#eff6ff' },
  navCta: { padding: '9px 18px', fontSize: 14, border: 'none', borderRadius: 9, background: BLUE, color: '#fff', cursor: 'pointer', fontWeight: 700 },
  flagBar: { height: 5, width: 120, margin: '0 auto 22px', borderRadius: 4, background: 'linear-gradient(90deg,#FCD116 0 33%,#003893 33% 66%,#CE1126 66%)' },
  hero: { maxWidth: 820, margin: '0 auto', padding: '52px 24px 28px', textAlign: 'center' },
  heroTitle: { fontSize: 38, lineHeight: 1.12, color: INK, fontWeight: 800, letterSpacing: '-0.02em', margin: '0 0 14px' },
  heroSub: { fontSize: 18, color: MUTE, maxWidth: 640, margin: '0 auto 28px', lineHeight: 1.5 },
  heroCta: { display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' },
  introBtn: { padding: '14px 28px', fontSize: 16, border: 'none', borderRadius: 10, background: BLUE, color: '#fff', cursor: 'pointer', fontWeight: 700 },
  introGhost: { padding: '14px 24px', fontSize: 16, border: `1px solid ${LINE}`, borderRadius: 10, background: '#fff', color: INK, cursor: 'pointer', fontWeight: 600 },
  block: { maxWidth: 980, margin: '0 auto', padding: '30px 24px' },
  h2: { fontSize: 26, fontWeight: 800, color: INK, textAlign: 'center', letterSpacing: '-0.01em', margin: 0 },
  h3: { fontSize: 17, fontWeight: 700, color: INK, margin: '28px 0 12px' },
  blockSub: { textAlign: 'center', color: MUTE, fontSize: 15, marginTop: 4, marginBottom: 22 },
  statsRow: { display: 'flex', gap: 28, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'center', background: '#f8fafc', border: `1px solid ${LINE}`, borderRadius: 16, padding: 24 },
  donutBox: { textAlign: 'center' },
  donutL: { width: 150, height: 150, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' },
  donutLTxt: { position: 'absolute', width: 106, height: 106, borderRadius: '50%', background: '#f8fafc', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26, fontWeight: 800, color: INK },
  donutCap: { marginTop: 10, fontSize: 13, color: MUTE, fontWeight: 600 },
  cardsGrid: { display: 'grid', gridTemplateColumns: 'repeat(2,minmax(150px,1fr))', gap: 14, flex: 1, minWidth: 320 },
  statCard: { background: '#fff', border: `1px solid ${LINE}`, borderRadius: 12, padding: '16px 18px' },
  statVal: { fontSize: 26, fontWeight: 800 }, statLbl: { fontSize: 13, color: MUTE, marginTop: 2 },
  stepGrid: { display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16, marginTop: 20 },
  stepCard: { background: '#fff', border: `1px solid ${LINE}`, borderRadius: 14, padding: 20, boxShadow: '0 1px 3px rgba(15,23,42,.06)' },
  stepNum: { width: 34, height: 34, borderRadius: '50%', background: BLUE, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, marginBottom: 12 },
  stepH: { fontSize: 16, fontWeight: 700, color: INK, marginBottom: 6 }, stepD: { fontSize: 14, color: MUTE, lineHeight: 1.5 },
  footer: { textAlign: 'center', padding: '30px 24px', color: '#94a3b8', fontSize: 13, borderTop: `1px solid ${LINE}`, marginTop: 24 },
  // tablero
  tableWrap: { maxWidth: 640, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 8 },
  boardRow: { display: 'flex', alignItems: 'center', gap: 14, padding: '12px 18px', background: '#fff', border: `1px solid ${LINE}`, borderRadius: 12 },
  boardTop: { background: '#fffbeb', borderColor: '#fde68a' },
  boardRank: { fontSize: 18, width: 30, textAlign: 'center', fontWeight: 800 },
  boardN: { color: BLUE, fontWeight: 700 },
  empty: { textAlign: 'center', color: MUTE, padding: 40, background: '#f8fafc', borderRadius: 12, border: `1px solid ${LINE}` },
  // fraude
  fraudeRow: { display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', background: '#fff', border: '1px solid #fecaca', borderRadius: 12 },
  actaIdSm: { fontFamily: 'ui-monospace,monospace', fontSize: 13, fontWeight: 700, color: INK }, actaInfoSm: { fontSize: 12, color: MUTE },
  nota: { fontSize: 13, color: '#b91c1c', fontStyle: 'italic', maxWidth: 280 }, reporter: { fontSize: 12, color: MUTE },
  // estadisticas
  statsTopGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 14, marginBottom: 8 },
  bigCard: { background: '#f8fafc', border: `1px solid ${LINE}`, borderRadius: 14, padding: '18px 20px', textAlign: 'center' },
  bigVal: { fontSize: 26, fontWeight: 800, color: INK }, bigLbl: { fontSize: 13, color: MUTE, marginTop: 4 },
  barsWrap: { display: 'flex', flexDirection: 'column', gap: 8 },
  barRow: { display: 'flex', alignItems: 'center', gap: 12 },
  barName: { width: 200, fontSize: 14, color: INK, textAlign: 'right', flexShrink: 0 },
  barTrack: { flex: 1, height: 22, background: '#f1f5f9', borderRadius: 6, overflow: 'hidden' },
  barFill: { height: '100%', borderRadius: 6 },
  barPct: { width: 56, fontSize: 14, fontWeight: 700, color: INK, textAlign: 'right' },
  barVotes: { width: 110, fontSize: 12, color: MUTE, textAlign: 'right' },
  disclaimer: { maxWidth: 760, margin: '24px auto 0', textAlign: 'center', color: MUTE, fontSize: 13.5, lineHeight: 1.6 },
  // verify
  app: { height: '100vh', display: 'flex', flexDirection: 'column', background: '#eef2f6' },
  vHeader: { display: 'flex', alignItems: 'center', gap: 14, padding: '10px 16px', background: '#fff', borderBottom: `1px solid ${LINE}` },
  backBtn: { fontSize: 13, padding: '7px 12px', border: `1px solid ${LINE}`, borderRadius: 8, background: '#fff', color: MUTE, cursor: 'pointer', fontWeight: 600 },
  progWrap: { display: 'flex', alignItems: 'center', gap: 10 }, progTrack: { width: 180, height: 8, background: LINE, borderRadius: 5, overflow: 'hidden' },
  progFill: { height: '100%', background: 'linear-gradient(90deg,#1d4ed8,#3b82f6)' }, progTxt: { fontSize: 13, color: MUTE, fontWeight: 600 },
  statBtn: { fontSize: 13, padding: '7px 14px', border: `1px solid ${LINE}`, borderRadius: 8, background: '#fff', color: INK, cursor: 'pointer', fontWeight: 600 },
  userChip: { fontSize: 13, color: BLUE, background: '#eff6ff', padding: '6px 12px', borderRadius: 20, fontWeight: 600 },
  main: { flex: 1, display: 'flex', minHeight: 0, padding: 16, gap: 16 },
  viewerCol: { flex: 1, display: 'flex', flexDirection: 'column', background: '#fff', borderRadius: 14, border: `1px solid ${LINE}`, overflow: 'hidden' },
  tabs: { display: 'flex', alignItems: 'center', gap: 8, padding: 10, borderBottom: `1px solid ${LINE}`, background: '#f8fafc' },
  tab: { padding: '8px 14px', fontSize: 13, border: `1px solid ${LINE}`, borderRadius: 8, background: '#fff', color: MUTE, cursor: 'pointer', fontWeight: 600 },
  tabActive: { background: BLUE, color: '#fff', borderColor: BLUE },
  viewerHint: { fontSize: 11, color: '#94a3b8' },
  canvas: { flex: 1, overflow: 'hidden', position: 'relative', background: '#f1f5f9' },
  loading: { padding: 40, color: MUTE },
  zoomCtl: { position: 'absolute', bottom: 14, left: 14, display: 'flex', gap: 6 },
  zoomBtn: { width: 36, height: 36, border: `1px solid ${LINE}`, borderRadius: 8, background: '#fff', color: INK, fontSize: 18, cursor: 'pointer' },
  panel: { width: 380, display: 'flex', flexDirection: 'column', background: '#fff', borderRadius: 14, border: `1px solid ${LINE}`, overflow: 'hidden' },
  panelHead: { padding: '14px 18px', borderBottom: `1px solid ${LINE}`, background: '#f8fafc' },
  actaId: { fontFamily: 'ui-monospace,monospace', fontSize: 13, fontWeight: 700, color: INK }, actaInfo: { fontSize: 12, color: MUTE, marginTop: 3 },
  fields: { flex: 1, overflowY: 'auto', padding: '8px 18px' },
  section: { fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em', color: '#94a3b8', fontWeight: 700, margin: '16px 0 6px' },
  fieldRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '5px 6px', borderRadius: 8 },
  fieldLabel: { fontSize: 14, color: '#334155' },
  fieldInput: { width: 72, padding: '8px', fontSize: 16, textAlign: 'center', border: '1.5px solid #cbd5e1', borderRadius: 8, color: INK, outline: 'none' },
  panelFoot: { padding: 14, borderTop: `1px solid ${LINE}`, background: '#fff' },
  status: { display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', borderRadius: 10, fontSize: 13.5, fontWeight: 600, marginBottom: 10 },
  ok: { background: '#f0fdf4', color: '#15803d', border: '1px solid #bbf7d0' },
  bad: { background: '#fef2f2', color: '#b91c1c', border: '1px solid #fecaca' },
  fraud: { background: '#dc2626', color: '#fff', border: '1px solid #dc2626' },
  neutral: { background: '#f8fafc', color: MUTE, border: `1px solid ${LINE}` },
  btnPrimary: { width: '100%', padding: 13, fontSize: 15, border: 'none', borderRadius: 10, background: BLUE, color: '#fff', cursor: 'pointer', fontWeight: 700 },
  btnDanger: { flex: 1, padding: 11, fontSize: 14, border: '1px solid #fca5a5', borderRadius: 10, background: '#fff', color: '#b91c1c', cursor: 'pointer', fontWeight: 700, marginTop: 8 },
  btnGhost: { padding: 11, fontSize: 14, border: `1px solid ${LINE}`, borderRadius: 10, background: '#fff', color: MUTE, cursor: 'pointer', fontWeight: 600, marginTop: 8 },
};
