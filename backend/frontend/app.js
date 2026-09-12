const API_BASE = ''; // mismo origen que sirve el frontend

let currentTicker = null;
let currentTimeframe = '1Y';
let chart, candleSeries, volumeSeries, emaSeries = {};

// ---------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------
function fmtMoney(v, currency = 'USD') {
  if (v === null || v === undefined || v === 'N/D') return 'N/D';
  const symbol = currency === 'USD' ? '$' : (currency + ' ');
  return symbol + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtPct(v, digits = 2) {
  if (v === null || v === undefined) return 'N/D';
  const n = Number(v);
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(digits)}%`;
}
function fmtNum(v, digits = 2) {
  if (v === null || v === undefined) return 'N/D';
  return Number(v).toFixed(digits);
}
function fmtBig(v) {
  if (v === null || v === undefined) return 'N/D';
  const n = Number(v);
  if (Math.abs(n) >= 1e12) return (n / 1e12).toFixed(2) + 'T';
  if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(2) + 'K';
  return n.toFixed(2);
}
function pillClass(color) {
  return { green: 'pill-green', red: 'pill-red', yellow: 'pill-yellow', gray: 'pill-gray' }[color] || 'pill-gray';
}
function chartColors() {
  const dark = document.documentElement.getAttribute('data-theme') !== 'light';
  return dark
    ? { bg: 'transparent', text: '#8B93A7', grid: '#1c2230', border: '#232838' }
    : { bg: 'transparent', text: '#5A6273', grid: '#eef0f5', border: '#E1E5EE' };
}

// ---------------------------------------------------------------------
// Tema
// ---------------------------------------------------------------------
document.getElementById('theme-toggle').addEventListener('click', () => {
  const html = document.documentElement;
  const isDark = html.getAttribute('data-theme') !== 'light';
  html.setAttribute('data-theme', isDark ? 'light' : 'dark');
  document.getElementById('theme-toggle').textContent = isDark ? '☀️' : '🌙';
  if (chart) applyChartTheme();
});

// ---------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    ['analysis', 'market', 'compare', 'scanner', 'risk', 'history', 'portfolio'].forEach(tab => {
      document.getElementById('tab-' + tab).classList.toggle('hidden', tab !== btn.dataset.tab);
    });
    if (btn.dataset.tab === 'history') renderHistory();
  });
});

// ---------------------------------------------------------------------
// Análisis principal
// ---------------------------------------------------------------------
document.getElementById('ticker-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const ticker = document.getElementById('ticker-input').value.trim().toUpperCase();
  if (!ticker) return;
  currentTicker = ticker;
  loadAnalysis(ticker, currentTimeframe);
});

document.querySelectorAll('.tf-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (!currentTicker) return;
    document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentTimeframe = btn.dataset.tf;
    loadAnalysis(currentTicker, currentTimeframe);
  });
});

async function loadAnalysis(ticker, timeframe) {
  document.getElementById('analysis-empty').classList.add('hidden');
  document.getElementById('analysis-error').classList.add('hidden');
  document.getElementById('analysis-content').classList.add('hidden');
  document.getElementById('analysis-loading').classList.remove('hidden');
  document.getElementById('analyze-btn').disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/analyze/${encodeURIComponent(ticker)}?timeframe=${timeframe}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Error desconocido' }));
      throw new Error(err.detail || 'No se pudo obtener el análisis.');
    }
    const data = await res.json();
    renderAnalysis(data);
    document.getElementById('analysis-content').classList.remove('hidden');
  } catch (err) {
    document.getElementById('analysis-error').textContent = err.message;
    document.getElementById('analysis-error').classList.remove('hidden');
  } finally {
    document.getElementById('analysis-loading').classList.add('hidden');
    document.getElementById('analyze-btn').disabled = false;
  }
}

let lastAnalysisData = null;

function renderAnalysis(d) {
  lastAnalysisData = d;
  const currency = d.quote.currency || 'USD';

  // Header
  document.getElementById('company-sector').textContent =
    `${d.company.sector || 'N/D'} — ${d.company.industry || 'N/D'}`;
  document.getElementById('company-name').textContent = `${d.company.name} (${d.ticker})`;
  document.getElementById('company-exchange').textContent = d.company.exchange || 'N/D';
  document.getElementById('quote-price').textContent = fmtMoney(d.quote.price, currency);
  const changeEl = document.getElementById('quote-change');
  changeEl.textContent = fmtPct(d.quote.change_pct);
  changeEl.style.color = (d.quote.change_pct || 0) >= 0 ? 'var(--green)' : 'var(--red)';
  document.getElementById('quote-mcap').textContent = fmtBig(d.quote.market_cap);
  document.getElementById('quote-volume').textContent = `Vol: ${fmtBig(d.quote.volume)} (prom. ${fmtBig(d.volume.average_20d)})`;
  document.getElementById('quote-52w').textContent = `${fmtMoney(d.quote.week52_low, currency)} – ${fmtMoney(d.quote.week52_high, currency)}`;
  document.getElementById('quote-updated').textContent = 'Actualizado: ' + new Date(d.quote.as_of).toLocaleString();

  // Tendencia
  const trends = d.trends;
  const trendRows = ['short_term', 'medium_term', 'long_term'].map(k => {
    const label = { short_term: 'Corto plazo', medium_term: 'Mediano plazo', long_term: 'Largo plazo' }[k];
    const t = trends[k];
    return `<div style="display:flex;justify-content:space-between;padding:6px 0;">
      <span class="stat-sub">${label}</span>
      <span class="pill ${pillClass(t.color)}">${t.label}</span>
    </div>`;
  }).join('');
  document.getElementById('trend-rows').innerHTML = trendRows;

  // Score
  document.getElementById('score-total').textContent = d.score.total;
  const scorePill = document.getElementById('score-pill');
  scorePill.textContent = d.score.label;
  scorePill.className = 'pill ' + pillClass(d.score.color);

  // Dirección sugerida (LONG / SHORT)
  const dirEl = document.getElementById('direction-value');
  const dir = d.direction.direction;
  const dirIcon = dir === 'LONG' ? '🟢' : dir === 'SHORT' ? '🔴' : '🟡';
  dirEl.textContent = `${dirIcon} ${dir}`;
  dirEl.style.color = d.direction.color === 'green' ? 'var(--green)' : d.direction.color === 'red' ? 'var(--red)' : 'var(--amber)';
  document.getElementById('score-long-mini').textContent = `${d.score.total} (${d.score.label})`;
  document.getElementById('score-short-mini').textContent = `${d.short_score.total} (${d.short_score.label})`;

  // Señal
  const sigEl = document.getElementById('signal-value');
  sigEl.textContent = (d.signal.signal === 'COMPRA' ? '🟢 ' : d.signal.signal === 'ESPERAR' ? '🟡 ' : '🔴 ') + d.signal.signal;
  sigEl.style.color = d.signal.color === 'green' ? 'var(--green)' : d.signal.color === 'red' ? 'var(--red)' : 'var(--amber)';

  // Estilo de trade
  document.getElementById('trade-style-value').textContent = d.trade_style.style;
  document.getElementById('trade-style-reason').textContent = d.trade_style.reason;

  // Breakout
  document.getElementById('breakout-score').textContent = d.breakout.score;
  const breakoutPill = document.getElementById('breakout-pill');
  breakoutPill.textContent = d.breakout.label;
  breakoutPill.className = 'pill ' + pillClass(d.breakout.color);
  document.getElementById('breakout-flags').innerHTML = d.breakout.flags.length
    ? d.breakout.flags.map(f => `• ${f}`).join('<br>')
    : 'Sin señales de ruptura detectadas ahora mismo.';

  // Precio objetivo
  document.getElementById('pt-current').textContent = fmtMoney(d.quote.price, currency);
  document.getElementById('pt-conservative').textContent = fmtMoney(d.price_target.conservative, currency);
  document.getElementById('pt-base').textContent = fmtMoney(d.price_target.base, currency);
  document.getElementById('pt-optimistic').textContent = fmtMoney(d.price_target.optimistic, currency);
  document.getElementById('pt-upside').textContent = fmtPct(d.price_target.upside_pct);
  document.getElementById('pt-upside').style.color = (d.price_target.upside_pct || 0) >= 0 ? 'var(--green)' : 'var(--red)';
  document.getElementById('pt-note').textContent = d.price_target.note;

  // Soportes / Resistencias
  document.getElementById('resistances-table').innerHTML = d.levels.resistances.length
    ? d.levels.resistances.map(r => `<tr><td class="text-cell">${r.label}</td><td>${fmtMoney(r.price, currency)}</td><td>${fmtPct(r.distance_pct)}</td><td class="text-cell">${r.strength}</td></tr>`).join('')
    : '<tr><td class="text-cell" colspan="4">No se detectaron resistencias claras.</td></tr>';
  document.getElementById('supports-table').innerHTML = d.levels.supports.length
    ? d.levels.supports.map(s => `<tr><td class="text-cell">${s.label}</td><td>${fmtMoney(s.price, currency)}</td><td>${fmtPct(s.distance_pct)}</td><td class="text-cell">${s.strength}</td></tr>`).join('')
    : '<tr><td class="text-cell" colspan="4">No se detectaron soportes claros.</td></tr>';

  // Fibonacci
  if (d.fibonacci) {
    document.getElementById('fib-context').textContent =
      `Movimiento ${d.fibonacci.direction} entre ${fmtMoney(d.fibonacci.swing_low, currency)} (${d.fibonacci.swing_low_date}) y ${fmtMoney(d.fibonacci.swing_high, currency)} (${d.fibonacci.swing_high_date}).`;
    document.getElementById('fib-table').innerHTML = d.fibonacci.levels.map(l =>
      `<tr><td>${(l.ratio * 100).toFixed(1)}%</td><td>${fmtMoney(l.price, currency)}</td><td class="text-cell">${l.matches_sr || '—'}</td></tr>`
    ).join('');
  } else {
    document.getElementById('fib-context').textContent = 'No hay datos suficientes para calcular Fibonacci.';
    document.getElementById('fib-table').innerHTML = '';
  }

  // Conclusión — usa el lado LONG o SHORT según la dirección sugerida
  const isShort = dir === 'SHORT';
  const c = isShort ? d.short_conclusion : d.conclusion;
  const conclusionLabel = isShort ? `🔴 SHORT (score ${d.short_score.total})` : (
    (d.signal.signal === 'COMPRA' ? '🟢 ' : d.signal.signal === 'ESPERAR' ? '🟡 ' : '🔴 ') + d.signal.signal
  );
  document.getElementById('conclusion-signal').textContent = conclusionLabel;
  document.getElementById('conclusion-signal').style.color = isShort ? 'var(--red)' : (d.signal.color === 'green' ? 'var(--green)' : d.signal.color === 'red' ? 'var(--red)' : 'var(--amber)');
  document.getElementById('conclusion-meta').innerHTML = isShort ? `
    <div>Tendencia: <b>${trends.medium_term.label}</b></div>
    <div>Lado: <b>SHORT (venta en corto)</b></div>
    <div>Riesgo: <b>${c.risk}</b></div>
  ` : `
    <div>Tendencia: <b>${trends.medium_term.label}</b></div>
    <div>Fundamentales: <b>${c.fundamentals}</b></div>
    <div>Valuación: <b>${c.valuation}</b></div>
    <div>Riesgo: <b>${c.risk}</b></div>
  `;

  document.getElementById('entry-range').textContent =
    c.entry_range[0] != null ? `${fmtMoney(c.entry_range[0], currency)} - ${fmtMoney(c.entry_range[1], currency)}` : 'N/D';
  document.getElementById('stop-loss').textContent = fmtMoney(c.stop_loss, currency);
  document.getElementById('targets').textContent = c.targets.length ? c.targets.map(t => fmtMoney(t, currency)).join(' / ') : 'N/D';
  document.getElementById('risk-reward').textContent = c.risk_reward ? `1:${c.risk_reward}` : 'N/D';
  document.getElementById('invalidation-text').textContent = c.invalidation;

  // Estrategias — LONG o SHORT según la dirección
  const stratNames = { conservadora: 'Conservadora', moderada: 'Moderada', agresiva: 'Agresiva' };
  const stratSource = isShort ? d.short_strategies : d.strategies;
  document.getElementById('strategies-grid').innerHTML = Object.entries(stratSource).map(([key, s]) => {
    if (!s) return `<div class="strategy-card"><h4>${stratNames[key]}</h4><p>Datos insuficientes para calcular esta estrategia.</p></div>`;
    return `<div class="strategy-card">
      <h4>${stratNames[key]} ${isShort ? '(short)' : ''}</h4>
      <p>${s.descripcion}</p>
      <div class="strategy-row"><span>Entrada</span><span>${fmtMoney(s.entrada, currency)}</span></div>
      <div class="strategy-row"><span>Stop</span><span>${fmtMoney(s.stop, currency)}</span></div>
      <div class="strategy-row"><span>Objetivo</span><span>${fmtMoney(s.objetivo, currency)}</span></div>
      <div class="strategy-row"><span>Riesgo %</span><span>${fmtNum(s.riesgo_pct)}%</span></div>
      <div class="strategy-row"><span>Potencial %</span><span>${fmtNum(s.potencial_pct)}%</span></div>
      <div class="strategy-row"><span>Risk/Reward</span><span>1:${fmtNum(s.risk_reward)}</span></div>
    </div>`;
  }).join('');

  // Indicadores técnicos
  document.getElementById('ind-rsi').textContent = fmtNum(d.oscillators.rsi);
  document.getElementById('ind-rsi-interp').textContent = d.oscillators.rsi_interpretation;
  document.getElementById('ind-macd').textContent =
    `${fmtNum(d.oscillators.macd_line, 3)} / ${fmtNum(d.oscillators.macd_signal, 3)}`;
  document.getElementById('ind-macd-interp').textContent =
    `${d.oscillators.macd_state.cross} · hist. ${d.oscillators.macd_state.histogram} · ${d.oscillators.macd_divergence}`;
  document.getElementById('ind-adx').textContent = fmtNum(d.volatility.adx);
  document.getElementById('ind-adx-interp').textContent = d.volatility.adx_interpretation;
  document.getElementById('ind-atr').textContent = fmtMoney(d.volatility.atr, currency);
  document.getElementById('ind-bb').textContent =
    `Sup ${fmtMoney(d.volatility.bollinger_upper, currency)} · Med ${fmtMoney(d.volatility.bollinger_mid, currency)} · Inf ${fmtMoney(d.volatility.bollinger_lower, currency)}`;
  document.getElementById('ind-stoch').textContent = `%K ${fmtNum(d.oscillators.stochastic_rsi_k)} / %D ${fmtNum(d.oscillators.stochastic_rsi_d)}`;
  document.getElementById('ind-vol').textContent =
    `${fmtBig(d.volume.current)} vs ${fmtBig(d.volume.average_20d)} ${d.volume.abnormal ? '🚨 anormal' : ''}`;
  document.getElementById('ind-vwap').textContent = fmtMoney(d.volume.vwap_60d, currency);

  document.getElementById('ma-row').innerHTML = ['ema9', 'ema20', 'ema50', 'ema100', 'ema200', 'sma20', 'sma50', 'sma200']
    .map(k => `<td>${fmtMoney(d.moving_averages[k], currency)}</td>`).join('');

  // Alertas
  document.getElementById('alerts-list').innerHTML = d.alerts.length
    ? d.alerts.map(a => `<div class="alert-item">🚨 ${a}</div>`).join('')
    : 'Sin alertas activas en este momento.';

  // Score breakdown
  const breakdownLabels = {
    tendencia_ema: ['Tendencia EMA', 25], momentum_macd: ['Momentum MACD', 15], rsi: ['RSI', 10],
    soportes_resistencias: ['Soportes/Resistencias', 10], volumen: ['Volumen', 10],
    fundamentales: ['Fundamentales', 15], valuacion: ['Valuación', 5],
  };
  document.getElementById('score-breakdown').innerHTML = Object.entries(d.score.breakdown).map(([k, v]) => {
    const [label, max] = breakdownLabels[k];
    const pct = (v / max) * 100;
    return `<div class="score-bar-row">
      <span class="score-bar-label">${label}</span>
      <div class="score-bar-track"><div class="score-bar-fill" style="width:${pct}%"></div></div>
      <span class="score-bar-val">${v}/${max}</span>
    </div>`;
  }).join('');

  // Fundamentales
  const fundLabels = {
    revenue: 'Revenue', revenue_growth: 'Revenue Growth', eps_ttm: 'EPS (TTM)', eps_forward: 'EPS Forward',
    ebitda: 'EBITDA', gross_margin: 'Margen Bruto', operating_margin: 'Margen Operativo', net_margin: 'Margen Neto',
    free_cash_flow: 'Free Cash Flow', total_debt: 'Deuda Total', total_cash: 'Cash', debt_to_equity: 'Debt/Equity',
    roe: 'ROE', roa: 'ROA', roic: 'ROIC', pe_trailing: 'P/E', pe_forward: 'Forward P/E', peg_ratio: 'PEG',
    ps_ratio: 'P/S', pb_ratio: 'P/B', ev_to_ebitda: 'EV/EBITDA', dividend_yield: 'Dividend Yield',
    payout_ratio: 'Payout Ratio', beta: 'Beta',
  };
  const pctFields = new Set(['revenue_growth', 'gross_margin', 'operating_margin', 'net_margin', 'roe', 'roa', 'roic', 'dividend_yield', 'payout_ratio']);
  const bigFields = new Set(['revenue', 'ebitda', 'free_cash_flow', 'total_debt', 'total_cash']);
  document.querySelector('#fundamentals-table tbody').innerHTML = Object.entries(fundLabels).map(([k, label]) => {
    let v = d.fundamentals[k];
    let display = 'N/D';
    if (v !== null && v !== undefined) {
      if (pctFields.has(k)) display = (v * 100).toFixed(2) + '%';
      else if (bigFields.has(k)) display = fmtBig(v);
      else display = fmtNum(v);
    }
    return `<tr><td class="text-cell">${label}</td><td>${display}</td></tr>`;
  }).join('');

  // Gráfico
  renderChart(d);

  // Guardar en el historial local (no consume cuota de la API)
  saveToHistory(d);
}

// ---------------------------------------------------------------------
// Historial de análisis y señales (guardado en localStorage del navegador)
// ---------------------------------------------------------------------
const HISTORY_KEY = 'stocklens_history_v1';
const HISTORY_MAX_ENTRIES = 300;

function saveToHistory(d) {
  try {
    const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    history.unshift({
      date: new Date().toISOString(),
      ticker: d.ticker,
      price: d.quote.price,
      currency: d.quote.currency,
      direction: d.direction.direction,
      direction_color: d.direction.color,
      score_long: d.score.total,
      score_short: d.short_score.total,
      signal: d.signal.signal,
    });
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, HISTORY_MAX_ENTRIES)));
  } catch (e) {
    console.warn('No se pudo guardar en el historial local:', e);
  }
}

function renderHistory() {
  let history = [];
  try {
    history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
  } catch (e) {
    history = [];
  }
  const tbody = document.getElementById('history-table-body');
  const emptyEl = document.getElementById('history-empty');
  if (!history.length) {
    tbody.innerHTML = '';
    emptyEl.classList.remove('hidden');
    return;
  }
  emptyEl.classList.add('hidden');
  tbody.innerHTML = history.map(h => {
    const dirColorVar = h.direction_color === 'green' ? 'var(--green)' : h.direction_color === 'red' ? 'var(--red)' : 'var(--amber)';
    const dt = new Date(h.date);
    return `<tr>
      <td class="text-cell">${dt.toLocaleDateString()} ${dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
      <td class="text-cell">${h.ticker}</td>
      <td>${fmtMoney(h.price, h.currency)}</td>
      <td class="text-cell" style="color:${dirColorVar};font-weight:600;">${h.direction}</td>
      <td>${h.score_long}</td>
      <td>${h.score_short}</td>
      <td class="text-cell">${h.signal}</td>
    </tr>`;
  }).join('');
}

document.getElementById('clear-history-btn').addEventListener('click', () => {
  if (confirm('¿Seguro que querés borrar todo el historial guardado en este navegador?')) {
    localStorage.removeItem(HISTORY_KEY);
    renderHistory();
  }
});

// ---------------------------------------------------------------------
// Alertas por Telegram (probar conexión / ejecutar chequeo manual)
// ---------------------------------------------------------------------
document.getElementById('test-telegram-btn').addEventListener('click', async () => {
  const el = document.getElementById('telegram-test-result');
  el.textContent = 'Enviando...';
  try {
    const res = await fetch(`${API_BASE}/api/alerts/test-telegram`, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'No se pudo enviar.');
    el.textContent = '✅ Mensaje de prueba enviado. Revisá tu Telegram.';
  } catch (err) {
    el.textContent = '❌ ' + err.message;
  }
});

document.getElementById('run-alerts-now-btn').addEventListener('click', async () => {
  if (!confirm('Esto va a analizar todos los tickers de ALERT_TICKERS ahora mismo, consumiendo cuota de la API. ¿Continuar?')) return;
  const el = document.getElementById('telegram-test-result');
  el.textContent = 'Ejecutando chequeo... esto puede tardar varios minutos según cuántos tickers tengas configurados.';
  try {
    const res = await fetch(`${API_BASE}/api/alerts/run-now`, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'No se pudo ejecutar.');
    el.innerHTML = `
      <div>✅ Enviados: ${data.sent.join(', ') || 'ninguno'}</div>
      <div>Sin señal clara u omitidos: ${data.skipped.join(', ') || 'ninguno'}</div>
      ${data.errors.length ? `<div style="color:var(--red)">Errores: ${data.errors.join('; ')}</div>` : ''}
    `;
  } catch (err) {
    el.textContent = '❌ ' + err.message;
  }
});

// ---------------------------------------------------------------------
// Gráfico (lightweight-charts)
// ---------------------------------------------------------------------
function applyChartTheme() {
  const colors = chartColors();
  chart.applyOptions({
    layout: { background: { color: colors.bg }, textColor: colors.text },
    grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
    rightPriceScale: { borderColor: colors.border },
    timeScale: { borderColor: colors.border },
  });
}

function renderChart(d) {
  const container = document.getElementById('chart-container');
  const volContainer = document.getElementById('volume-container');
  container.innerHTML = '';
  volContainer.innerHTML = '';

  const colors = chartColors();

  chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: 460,
    layout: { background: { color: colors.bg }, textColor: colors.text },
    grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
    rightPriceScale: { borderColor: colors.border },
    timeScale: { borderColor: colors.border, timeVisible: currentTimeframe === '1D' || currentTimeframe === '1W' },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });

  candleSeries = chart.addCandlestickSeries({
    upColor: '#2FD98A', downColor: '#FF5C72', borderVisible: false,
    wickUpColor: '#2FD98A', wickDownColor: '#FF5C72',
  });
  candleSeries.setData(d.chart.candles.map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })));

  const emaColors = { ema9: '#4C8DFF', ema20: '#F0B429', ema50: '#B389FF', ema200: '#FF5C72' };
  emaSeries = {};
  Object.entries(d.chart.ema_overlays).forEach(([key, points]) => {
    if (!points.length) return;
    const s = chart.addLineSeries({ color: emaColors[key], lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false });
    s.setData(points);
    emaSeries[key] = s;
  });

  // Soportes / resistencias como líneas de precio
  d.chart.supports.forEach(price => {
    candleSeries.createPriceLine({ price, color: '#2FD98A', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, title: 'Soporte' });
  });
  d.chart.resistances.forEach(price => {
    candleSeries.createPriceLine({ price, color: '#FF5C72', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, title: 'Resistencia' });
  });

  // Volumen en panel separado
  const volChart = LightweightCharts.createChart(volContainer, {
    width: volContainer.clientWidth,
    height: 110,
    layout: { background: { color: colors.bg }, textColor: colors.text },
    grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
    rightPriceScale: { borderColor: colors.border },
    timeScale: { borderColor: colors.border, visible: false },
  });
  volumeSeries = volChart.addHistogramSeries({ color: '#4C8DFF' });
  volumeSeries.setData(d.chart.candles.map(c => ({
    time: c.time, value: c.volume, color: c.close >= c.open ? 'rgba(47,217,138,.5)' : 'rgba(255,92,114,.5)',
  })));

  chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
    if (range) volChart.timeScale().setVisibleLogicalRange(range);
  });

  window.addEventListener('resize', () => {
    chart.applyOptions({ width: container.clientWidth });
    volChart.applyOptions({ width: volContainer.clientWidth });
  });
}

// ---------------------------------------------------------------------
// Panel de mercado general
// ---------------------------------------------------------------------
document.getElementById('market-refresh-btn').addEventListener('click', async () => {
  document.getElementById('market-error').classList.add('hidden');
  document.getElementById('market-content').classList.add('hidden');
  document.getElementById('market-loading').classList.remove('hidden');
  try {
    const res = await fetch(`${API_BASE}/api/market-overview`);
    if (!res.ok) throw new Error('No se pudo obtener el panel de mercado.');
    const data = await res.json();
    const ctxEl = document.getElementById('market-context-value');
    ctxEl.textContent = data.context.label;
    ctxEl.style.color = data.context.color === 'green' ? 'var(--green)' : data.context.color === 'red' ? 'var(--red)' : 'var(--amber)';
    document.getElementById('market-cards').innerHTML = data.symbols.map(s => {
      if (s.error) {
        return `<div class="card"><div class="card-title">${s.label}</div><div class="stat-sub">${s.error}</div></div>`;
      }
      const color = (s.change_pct || 0) >= 0 ? 'var(--green)' : 'var(--red)';
      return `<div class="card">
        <div class="card-title">${s.label}</div>
        <div class="stat-value mono">${fmtMoney(s.price)}</div>
        <div class="stat-sub" style="color:${color}">${fmtPct(s.change_pct)}</div>
        <div class="stat-sub">Rango: ${fmtMoney(s.day_low)} - ${fmtMoney(s.day_high)}</div>
        <div class="stat-sub">Al ${s.as_of_date}</div>
      </div>`;
    }).join('');
    document.getElementById('market-content').classList.remove('hidden');
  } catch (err) {
    document.getElementById('market-error').textContent = err.message;
    document.getElementById('market-error').classList.remove('hidden');
  } finally {
    document.getElementById('market-loading').classList.add('hidden');
  }
});
document.getElementById('compare-btn').addEventListener('click', async () => {
  const raw = document.getElementById('compare-input').value.trim();
  if (!raw) return;
  document.getElementById('compare-error').classList.add('hidden');
  document.getElementById('compare-results').classList.add('hidden');
  document.getElementById('compare-loading').classList.remove('hidden');
  try {
    const res = await fetch(`${API_BASE}/api/compare?tickers=${encodeURIComponent(raw)}`);
    if (!res.ok) throw new Error('No se pudo calcular la comparación.');
    const data = await res.json();
    document.getElementById('compare-table-body').innerHTML = data.tickers.map(t => {
      if (t.error) return `<tr><td class="text-cell">${t.ticker}</td><td colspan="10" class="text-cell">${t.error}</td></tr>`;
      return `<tr>
        <td class="text-cell">${t.ticker}</td>
        <td>${fmtMoney(t.price)}</td>
        <td style="color:${(t.change_pct||0)>=0?'var(--green)':'var(--red)'}">${fmtPct(t.change_pct)}</td>
        <td>${fmtNum(t.rsi)}</td>
        <td>${fmtNum(t.pe_trailing)}</td>
        <td>${t.revenue_growth != null ? (t.revenue_growth*100).toFixed(1)+'%' : 'N/D'}</td>
        <td>${t.roe != null ? (t.roe*100).toFixed(1)+'%' : 'N/D'}</td>
        <td>${t.net_margin != null ? (t.net_margin*100).toFixed(1)+'%' : 'N/D'}</td>
        <td>${t.score}</td>
        <td>${fmtMoney(t.price_target_base)}</td>
        <td style="color:${(t.upside_pct||0)>=0?'var(--green)':'var(--red)'}">${fmtPct(t.upside_pct)}</td>
      </tr>`;
    }).join('');
    document.getElementById('compare-results').classList.remove('hidden');
  } catch (err) {
    document.getElementById('compare-error').textContent = err.message;
    document.getElementById('compare-error').classList.remove('hidden');
  } finally {
    document.getElementById('compare-loading').classList.add('hidden');
  }
});

// ---------------------------------------------------------------------
// Scanner de rupturas (Explosivas)
// ---------------------------------------------------------------------
document.getElementById('scanner-btn').addEventListener('click', async () => {
  const raw = document.getElementById('scanner-input').value.trim();
  if (!raw) return;
  document.getElementById('scanner-error').classList.add('hidden');
  document.getElementById('scanner-results').innerHTML = '';
  document.getElementById('scanner-loading').classList.remove('hidden');
  try {
    const res = await fetch(`${API_BASE}/api/scanner?tickers=${encodeURIComponent(raw)}`);
    if (!res.ok) throw new Error('No se pudo ejecutar el escaneo.');
    const data = await res.json();
    document.getElementById('scanner-results').innerHTML = data.results.map(r => {
      if (r.error) {
        return `<div class="card"><div class="card-title">${r.ticker}</div><div class="stat-sub">${r.error}</div></div>`;
      }
      return `<div class="card">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <div>
            <div style="font-size:17px;font-weight:700;">${r.ticker}</div>
            <div class="stat-sub">${fmtMoney(r.price)} · ${fmtPct(r.change_pct)}</div>
          </div>
          <span class="pill ${pillClass(r.breakout_color)}">${r.breakout_score}/100</span>
        </div>
        <div class="stat-sub" style="margin:8px 0 4px;font-weight:600;color:var(--text);">${r.breakout_label}</div>
        <div class="stat-sub" style="margin-bottom:10px;">
          ${r.breakout_flags.length ? r.breakout_flags.map(f => `• ${f}`).join('<br>') : 'Sin señales de ruptura detectadas.'}
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <span class="pill pill-gray">Score general: ${r.score}</span>
          <span class="pill pill-gray">${r.signal}</span>
          <span class="pill pill-gray">${r.trade_style}</span>
        </div>
      </div>`;
    }).join('');
  } catch (err) {
    document.getElementById('scanner-error').textContent = err.message;
    document.getElementById('scanner-error').classList.remove('hidden');
  } finally {
    document.getElementById('scanner-loading').classList.add('hidden');
  }
});
// ---------------------------------------------------------------------
// Calculadora de riesgo y tamaño de posición
// ---------------------------------------------------------------------
document.getElementById('risk-use-analysis-btn').addEventListener('click', () => {
  if (!lastAnalysisData) {
    alert('Primero analizá un ticker en la pestaña "Análisis" para poder traer sus precios acá.');
    return;
  }
  const d = lastAnalysisData;
  const entry = d.conclusion.entry_range && d.conclusion.entry_range[0] != null ? d.conclusion.entry_range[0] : d.quote.price;
  const stop = d.conclusion.stop_loss;
  const target = d.conclusion.targets && d.conclusion.targets.length ? d.conclusion.targets[0] : null;
  if (entry != null) document.getElementById('risk-entry').value = entry;
  if (stop != null) document.getElementById('risk-stop').value = stop;
  if (target != null) document.getElementById('risk-target').value = target;
});

document.getElementById('risk-calc-btn').addEventListener('click', () => {
  const capital = parseFloat(document.getElementById('risk-capital').value) || 0;
  const maxRiskPct = parseFloat(document.getElementById('risk-max-pct').value) || 0;
  const entry = parseFloat(document.getElementById('risk-entry').value);
  const stop = parseFloat(document.getElementById('risk-stop').value);
  const target = parseFloat(document.getElementById('risk-target').value);
  const commissionPct = parseFloat(document.getElementById('risk-commission').value) || 0;

  const resultsEl = document.getElementById('risk-results');

  if (!capital || !entry || !stop || entry === stop) {
    resultsEl.innerHTML = '<div class="stat-sub">Completá al menos Capital, Precio de entrada y Stop loss (distintos entre sí).</div>';
    return;
  }
  if (stop >= entry) {
    resultsEl.innerHTML = '<div class="risk-warning">⚠️ El stop loss debería estar por debajo del precio de entrada para una posición larga (compra). Revisá los valores.</div>';
    return;
  }

  const riskPerShare = entry - stop;
  const maxRiskMoney = capital * (maxRiskPct / 100);
  let shares = Math.floor(maxRiskMoney / riskPerShare);
  if (shares < 0) shares = 0;

  const positionValue = shares * entry;
  const commission = positionValue * (commissionPct / 100) * 2; // entrada + salida
  const maxLoss = shares * riskPerShare + commission;
  const exposurePct = capital ? (positionValue / capital * 100) : 0;

  let targetHtml = '';
  if (target && target > entry) {
    const potentialGain = shares * (target - entry) - commission;
    const rr = (target - entry) / riskPerShare;
    targetHtml = `
      <div class="risk-result-row"><span>Ganancia potencial (al objetivo)</span><span style="color:var(--green)">${fmtMoney(potentialGain)}</span></div>
      <div class="risk-result-row"><span>Relación riesgo/beneficio</span><span>1:${rr.toFixed(2)}</span></div>
    `;
  }

  let warnings = '';
  if (exposurePct > 25) {
    warnings += `<div class="risk-warning">⚠️ Esta posición representa el ${exposurePct.toFixed(0)}% de tu capital — es una concentración alta para una sola operación.</div>`;
  }
  if (shares === 0) {
    warnings += `<div class="risk-warning">⚠️ Con este riesgo máximo y esta distancia al stop, no alcanza ni para comprar 1 acción. Subí el riesgo permitido o achicá la distancia al stop.</div>`;
  }
  const stopDistancePct = (riskPerShare / entry) * 100;
  if (stopDistancePct < 0.5) {
    warnings += `<div class="risk-warning">⚠️ El stop está muy cerca del precio de entrada (${stopDistancePct.toFixed(2)}%) — hay riesgo de que te saque por simple ruido del mercado.</div>`;
  }

  resultsEl.innerHTML = `
    <div class="risk-result-row"><span>Cantidad de acciones sugerida</span><span>${shares}</span></div>
    <div class="risk-result-row"><span>Capital a utilizar</span><span>${fmtMoney(positionValue)}</span></div>
    <div class="risk-result-row"><span>Exposición sobre tu capital</span><span>${exposurePct.toFixed(1)}%</span></div>
    <div class="risk-result-row"><span>Riesgo por acción</span><span>${fmtMoney(riskPerShare)}</span></div>
    <div class="risk-result-row"><span>Pérdida máxima estimada</span><span style="color:var(--red)">${fmtMoney(maxLoss)}</span></div>
    <div class="risk-result-row"><span>% de tu capital en riesgo</span><span>${capital ? (maxLoss / capital * 100).toFixed(2) : '0'}%</span></div>
    ${targetHtml}
    ${warnings}
  `;
});

function addPortfolioRow(ticker = '', quantity = '', avgPrice = '') {
  const div = document.createElement('div');
  div.className = 'input-row';
  div.innerHTML = `
    <input type="text" name="ticker" placeholder="TICKER" value="${ticker}">
    <input type="number" name="quantity" placeholder="Cantidad" min="0" step="any" value="${quantity}">
    <input type="number" name="avg_price" placeholder="Precio promedio" min="0" step="any" value="${avgPrice}">
    <button type="button" class="remove-btn" title="Quitar">✕</button>
  `;
  div.querySelector('.remove-btn').addEventListener('click', () => div.remove());
  document.getElementById('portfolio-rows').appendChild(div);
}
document.getElementById('add-position-btn').addEventListener('click', () => addPortfolioRow());
addPortfolioRow(); addPortfolioRow();

document.getElementById('bulk-load-btn').addEventListener('click', () => {
  const raw = document.getElementById('bulk-portfolio-input').value.trim();
  if (!raw) return;
  const lines = raw.split('\n').map(l => l.trim()).filter(Boolean);
  if (lines.length > 15) {
    if (!confirm(`Vas a cargar ${lines.length} posiciones. Con el límite gratuito de 25 consultas/día, probablemente no todas se puedan analizar hoy. ¿Continuar de todas formas?`)) {
      return;
    }
  }
  document.getElementById('portfolio-rows').innerHTML = '';
  lines.forEach(line => {
    const parts = line.split(',').map(p => p.trim());
    const ticker = (parts[0] || '').toUpperCase();
    const quantity = parts[1] || '';
    const avgPrice = parts[2] || '0';
    if (ticker) addPortfolioRow(ticker, quantity, avgPrice);
  });
  document.getElementById('bulk-portfolio-input').value = '';
});

document.getElementById('calc-portfolio-btn').addEventListener('click', async () => {
  const rows = Array.from(document.querySelectorAll('#portfolio-rows .input-row'));
  const positions = rows.map(r => ({
    ticker: r.querySelector('[name="ticker"]').value.trim(),
    quantity: parseFloat(r.querySelector('[name="quantity"]').value) || 0,
    avg_price: parseFloat(r.querySelector('[name="avg_price"]').value) || 0,
  })).filter(p => p.ticker && p.quantity > 0);

  if (!positions.length) return;

  document.getElementById('portfolio-error').classList.add('hidden');
  document.getElementById('portfolio-results').classList.add('hidden');
  document.getElementById('portfolio-summary').classList.add('hidden');
  document.getElementById('portfolio-loading').classList.remove('hidden');

  try {
    const res = await fetch(`${API_BASE}/api/portfolio`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(positions),
    });
    if (!res.ok) throw new Error('No se pudo calcular la cartera.');
    const data = await res.json();
    document.getElementById('pf-total').textContent = fmtMoney(data.total_value);
    document.getElementById('portfolio-table-body').innerHTML = data.positions.map(p => {
      if (p.error) return `<tr><td class="text-cell">${p.ticker}</td><td colspan="9" class="text-cell">${p.error}</td></tr>`;
      return `<tr>
        <td class="text-cell">${p.ticker}</td><td>${p.quantity}</td><td>${fmtMoney(p.avg_price)}</td>
        <td>${fmtMoney(p.current_price)}</td><td>${fmtMoney(p.current_value)}</td>
        <td style="color:${p.gain_loss>=0?'var(--green)':'var(--red)'}">${fmtMoney(p.gain_loss)}</td>
        <td style="color:${p.gain_loss>=0?'var(--green)':'var(--red)'}">${fmtPct(p.gain_loss_pct)}</td>
        <td>${p.weight_pct != null ? p.weight_pct+'%' : 'N/D'}</td>
        <td>${p.score}</td><td>${fmtMoney(p.price_target_base)}</td>
      </tr>`;
    }).join('');
    document.getElementById('portfolio-summary').classList.remove('hidden');
    document.getElementById('portfolio-results').classList.remove('hidden');
  } catch (err) {
    document.getElementById('portfolio-error').textContent = err.message;
    document.getElementById('portfolio-error').classList.remove('hidden');
  } finally {
    document.getElementById('portfolio-loading').classList.add('hidden');
  }
});
