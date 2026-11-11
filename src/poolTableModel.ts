// 股票池「终端紧凑表格 + 持续跟踪 + 回测」展示层模型。
// 契约：docs/pool-table/contract.md §2.1/§2.2（表格/详情/回测）、§7-§8、§10-§12（瀑布流卡片 + 同义词分组 + driver_short）。
// 数据形状见 §1.2/§1.3；分组为前端计算，driver/fund 由后端并行接入，缺失统一降级为 —。
// 本文件只做展示派生，不改变后端口径；缺失数据显式显示 —/未到期/缺数据，不按 0 计。
export type Request = <T>(method: string, args?: Record<string, unknown>) => Promise<T>;

export type Plan = {
  buy_low: number | null; buy_high: number | null; chase: number | null; stop: number | null;
  target1: number | null; target2: number | null; trail: number | null; note: string | null; sell_note: string | null;
};
export type Quote = {price: number; percent: number; time: string; low?: number | null; high?: number | null; basis?: 'live' | 'last' | 'added'; fresh?: boolean};
export type HistoryRow = {
  day: string; price: number; percent: number; high: number | null; low: number | null;
  hit_buy: boolean; hit_stop: boolean; hit_target: boolean;
  turnover_rate?: number | null; volume_ratio?: number | null;
};
export type EntryWindow = {n?: number; date?: string | null; close?: number | null; return_percent?: number | null; benchmark_return?: number | null; excess_percent?: number | null};
export type Episodes = {total: number; today: number; first_at: string | null; last_at: string | null};
export type Quant = {turnover_rate: number | null; volume_ratio: number | null; amplitude: number | null; float_mcap_yi: number | null};
export type Tags = {concept: string[]; theme: string[]; event: string[]; other: string[]};
/** 契约 §8：driver = 该 code 最新一期研判的入选理由（截断）；fund = 东财主力净流入（缺失 None）。 */
export type Driver = {at: string | null; text: string | null};
export type Fund = {net: number | null; net_yi: number | null; rate: number | null; time: string | null};
export type Entry = {
  code: string; name: string; added_day: string; added_at?: string | null; added_price: number;
  source: string; sector: string; role: string; reason: string; state: string;
  entry_tag: string; category: string; group_name: string; groups?: string[]; group_rank?: number | null; group_size?: number | null;
  updated_at: string; plan: Plan | null; quote: Quote | null;
  today_percent: number | null; since_add_percent: number | null; distance_to_buy_percent: number | null; zone: string; hint: string;
  history: HistoryRow[]; max_gain_percent: number | null; max_drawdown_percent: number | null; hold_days: number | null;
  windows?: Record<string, EntryWindow | null> | null; holding_days?: number | null; holding_bucket?: string | null;
  episodes?: Partial<Episodes> | null; quant?: Partial<Quant> | null; tags?: Partial<Record<keyof Tags, unknown>> | null;
  driver?: Partial<Driver> | null; driver_short?: string | null; driver_short_at?: string | null; fund?: Partial<Fund> | null;
};
export type PoolData = {
  updated_at: string | null; quotes_time: string | null; trading?: boolean; error?: string;
  entries: Entry[]; filtered_total?: number; has_more?: boolean; offset?: number; limit?: number;
  benchmark?: string | null; archived_count?: number | null; [key: string]: unknown;
};

// ===== 表格排序 / 筛选 =====
export type SortKey = 'added' | 'entry' | 'since' | 'today' | 'ratio' | 'turnover' | 'episodes';
export type SortState = {key: SortKey; dir: 'asc' | 'desc'};
export const DEFAULT_SORT: SortState = {key: 'added', dir: 'desc'};
export const SORT_OPTIONS: {value: string; label: string; key: SortKey; dir: 'asc' | 'desc'}[] = [
  {value: 'added-desc', label: '入选时间 ↓', key: 'added', dir: 'desc'},
  {value: 'added-asc', label: '入选时间 ↑', key: 'added', dir: 'asc'},
  {value: 'since-desc', label: '入选收益 ↓', key: 'since', dir: 'desc'},
  {value: 'since-asc', label: '入选收益 ↑', key: 'since', dir: 'asc'},
  {value: 'today-desc', label: '涨幅 ↓', key: 'today', dir: 'desc'},
  {value: 'today-asc', label: '涨幅 ↑', key: 'today', dir: 'asc'},
  {value: 'ratio-desc', label: '量比 ↓', key: 'ratio', dir: 'desc'},
  {value: 'ratio-asc', label: '量比 ↑', key: 'ratio', dir: 'asc'},
  {value: 'turnover-desc', label: '换手 ↓', key: 'turnover', dir: 'desc'},
  {value: 'turnover-asc', label: '换手 ↑', key: 'turnover', dir: 'asc'},
  {value: 'episodes-desc', label: '入选天数 ↓', key: 'episodes', dir: 'desc'},
  {value: 'episodes-asc', label: '入选天数 ↑', key: 'episodes', dir: 'asc'},
  {value: 'entry-desc', label: '入选价格 ↓', key: 'entry', dir: 'desc'},
  {value: 'entry-asc', label: '入选价格 ↑', key: 'entry', dir: 'asc'},
];
export type RowChip = 'all' | 'today' | 'multi';
export type RowPeriod = 'all' | 'today' | '3d' | '5d';
export type RowFilter = {chip: RowChip; period: RowPeriod; search: string};
export const DEFAULT_ROW_FILTER: RowFilter = {chip: 'all', period: 'all', search: ''};
export const PERIOD_OPTIONS: {value: RowPeriod; label: string}[] = [
  {value: 'all', label: '全部时间'}, {value: 'today', label: '今日'}, {value: '3d', label: '近3日'}, {value: '5d', label: '近5日'},
];

export const STORAGE_KEY = 'stock-monitor-pool-terminal-v1';
export function readStoredTerminal(): {filter: RowFilter; sort: SortState} {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {filter: DEFAULT_ROW_FILTER, sort: DEFAULT_SORT};
    const parsed = JSON.parse(raw) as {filter?: Partial<RowFilter>; sort?: Partial<SortState>};
    const filter = {...DEFAULT_ROW_FILTER, ...(parsed.filter || {})};
    const sort = parsed.sort && parsed.sort.key && parsed.sort.dir ? {key: parsed.sort.key, dir: parsed.sort.dir} : DEFAULT_SORT;
    return {filter, sort};
  } catch {
    return {filter: DEFAULT_ROW_FILTER, sort: DEFAULT_SORT};
  }
}
export function writeStoredTerminal(state: {filter: RowFilter; sort: SortState}) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* 隐私模式忽略 */
  }
}

// ===== 数字/颜色/时间格式 =====
export const isNum = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
export const num2 = (value: number | null | undefined) => (isNum(value) ? value.toFixed(2) : '—');
export const pctSigned = (value: number | null | undefined, digits = 2) =>
  isNum(value) ? (value > 0 ? '+' : '') + value.toFixed(digits) + '%' : '—';
/** 涨红跌绿平灰：返回 up/down/flat/空 */
export const toneClass = (value: number | null | undefined) => (isNum(value) ? (value > 0 ? 'up' : value < 0 ? 'down' : 'flat') : '');
export const clockText = (value: string | null | undefined) => {
  if (!value) return '—';
  if (value.length >= 19) return value.slice(11, 19);
  if (value.length >= 16) return value.slice(11, 16);
  return value;
};
export const TIME_LABEL: Record<string, string> = {'0-3': '0–3%', '3-7': '3–7%', '7+': '7% 以上', lt0: '< 0%', '3+': '3 天及以上'};

/** 行内“时间（入选）”：MM-DD HH:MM，缺时间时退化为 MM-DD。 */
export function entryTime(entry: Entry) {
  if (entry.added_at && entry.added_at.length >= 16) return entry.added_at.slice(5, 10) + ' ' + entry.added_at.slice(11, 16);
  return entry.added_day ? entry.added_day.slice(5) : '—';
}
export const fullStamp = (value: string | null | undefined) => {
  if (!value) return '—';
  return value.length >= 16 ? value.slice(0, 10) + ' ' + value.slice(11, 16) : value;
};
export const shortStamp = (value: string | null | undefined) => {
  if (!value) return '—';
  return value.length >= 16 ? value.slice(5, 10) + ' ' + value.slice(11, 16) : value;
};
export const dayShort = (value: string | null | undefined) => (value ? value.slice(5) : '—');

// ===== 入选次数 / 量比换手 / 标签 =====
export function episodesOf(entry: Entry): Episodes {
  const raw = entry.episodes;
  const total = Number(raw && typeof raw === 'object' ? raw.total : NaN);
  if (Number.isFinite(total)) {
    return {
      total,
      today: Number.isFinite(Number(raw?.today)) ? Number(raw?.today) : 0,
      first_at: typeof raw?.first_at === 'string' ? raw.first_at : null,
      last_at: typeof raw?.last_at === 'string' ? raw.last_at : null,
    };
  }
  // 兜底：episodes 尚未接入时，至少按 pool 行自身算 1 天，避免整列空白。
  return {total: 1, today: 0, first_at: entry.added_at ?? null, last_at: entry.added_at ?? null};
}
export function episodesTitle(entry: Entry) {
  const episodes = episodesOf(entry);
  const todayText = episodes.today > 0 ? '今日已入选' : '今日未入选';
  return '累计 ' + episodes.total + ' 天 · ' + todayText + ' · 首次 ' + fullStamp(episodes.first_at) + ' · 最近 ' + fullStamp(episodes.last_at);
}
export function quantOf(entry: Entry): Quant {
  const raw = entry.quant;
  const pick = (key: keyof Quant) => {
    const value = raw && typeof raw === 'object' ? raw[key] : null;
    return isNum(value) ? value : null;
  };
  return {turnover_rate: pick('turnover_rate'), volume_ratio: pick('volume_ratio'), amplitude: pick('amplitude'), float_mcap_yi: pick('float_mcap_yi')};
}
const listOf = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim())).map(item => item.trim()) : [];
const uniq4 = (values: string[]) => [...new Set(values.filter(Boolean))].slice(0, 4);
/** 概念/题材/事件标签：优先后端 tags；缺失时按 category/group_name/groups/sector 兜底。 */
export function tagsOf(entry: Entry): Tags {
  const raw = entry.tags;
  if (raw && typeof raw === 'object') {
    return {concept: uniq4(listOf(raw.concept)), theme: uniq4(listOf(raw.theme)), event: uniq4(listOf(raw.event)), other: uniq4(listOf(raw.other))};
  }
  const names = uniq4([entry.group_name, ...(entry.groups ?? [])].filter(Boolean));
  const tags: Tags = {concept: [], theme: [], event: [], other: []};
  const category = entry.category || '';
  if (category === '概念') tags.concept = names;
  else if (category === '题材' || category === '名称辈' || category === '生肖玄学') tags.theme = names;
  else if (category === '事件') tags.event = names;
  else tags.other = uniq4([...names, entry.sector]);
  return tags;
}
export function tagsTitle(tags: string[]) {
  return tags.length ? tags.join(' · ') : '—';
}
/** 契约 §7：相关概念/题材 = theme+concept+event+other 去重（显示前 3 个，title 全量）。 */
export function relatedTagsOf(entry: Entry): string[] {
  const tags = tagsOf(entry);
  const all = [...tags.theme, ...tags.concept, ...tags.event, ...tags.other]
    .map(token => String(token || '').trim())
    .filter(token => token && !NOISE_TOKENS.includes(token));
  return [...new Set(all)];
}
export function relatedTagsText(entry: Entry) {
  const all = relatedTagsOf(entry);
  if (all.length) return all.slice(0, 3).join(' / ');
  const sector = String(entry.sector || '').trim();
  if (sector && !NOISE_TOKENS.includes(sector)) return sector;
  return '—';
}
export function relatedTagsTitle(entry: Entry) {
  const all = relatedTagsOf(entry);
  return all.length ? all.join(' · ') : '—';
}

// ===== 契约 §8：driver / fund（后端并行接入，缺失优雅降级） =====
export function driverOf(entry: Entry): Driver {
  const raw = entry.driver;
  return {
    at: raw && typeof raw.at === 'string' && raw.at ? raw.at : null,
    text: raw && typeof raw.text === 'string' && raw.text.trim() ? raw.text.trim() : null,
  };
}
export function fundOf(entry: Entry): Fund {
  const raw = entry.fund;
  const pick = (key: keyof Fund) => (raw && typeof raw === 'object' && isNum(raw[key]) ? raw[key] as number : null);
  return {net: pick('net'), net_yi: pick('net_yi'), rate: pick('rate'), time: raw && typeof raw.time === 'string' ? raw.time : null};
}
/** 组级资金求和口径：优先 net_yi，其次 net/1e8；都缺失返回 null。 */
export function fundYiOf(entry: Entry): number | null {
  const fund = fundOf(entry);
  if (isNum(fund.net_yi)) return fund.net_yi;
  if (isNum(fund.net)) return fund.net / 1e8;
  return null;
}
/** 驱动文案：去「方向：」前缀、截断 60 字（后端 driver.text 已是该 code 最新 episode reason）。 */
export function driverTextOf(driver: Driver | null | undefined, fallback?: string | null) {
  const raw = (driver?.text || fallback || '').trim();
  if (!raw) return null;
  const stripped = raw.replace(/^方向[：:]\s*/, '').trim();
  if (!stripped) return null;
  return stripped.length > 60 ? stripped.slice(0, 60) + '…' : stripped;
}
/** 契约 §12.1/§12.2：把 driver/reason 压成组头用的短原因（优先后端 driver_short）。 */
export function compressDriverText(text: string | null | undefined) {
  const raw = (text || '').trim().replace(/^方向[：:]\s*/, '');
  if (!raw) return null;
  if (raw.includes('板块上涨') && raw.includes('净流入')) return '板块上涨、资金净流入';
  if (/只观察[，,]?\s*不追高/.test(raw)) return '只观察不追高';
  if (raw.includes('涨停待回踩')) return '涨停待回踩';
  if (raw.includes('回踩低吸')) return '回踩低吸';
  if (/加速|高潮/.test(raw)) return '加速期';
  if (raw.includes('发酵')) return '题材发酵';
  const segments = raw.split(/[；;。]/).map(item => item.trim()).filter(Boolean);
  const last = segments.length ? segments[segments.length - 1] : raw;
  return last.length > 20 ? last.slice(0, 20) + '…' : last;
}
/** 组头驱动：优先后端 driver_short；否则从 driver.text/reason 压缩；最长 28 字。 */
export function shortDriverOf(entry: Entry) {
  const direct = typeof entry.driver_short === 'string' ? entry.driver_short.trim() : '';
  const text = direct || compressDriverText(driverOf(entry).text) || compressDriverText(entry.reason) || '';
  if (!text) return null;
  return text.length > 28 ? text.slice(0, 28) + '…' : text;
}
/** 泛化驱动短句：组头优先展示更具体的 driver_short（如新闻标题），没有具体原因时才回退。 */
export const GENERIC_DRIVER_SHORTS = new Set([
  '板块上涨、资金净流入', '只观察不追高', '回踩低吸', '涨停待回踩', '加速期', '题材发酵',
  '收盘时已走强，下一交易日开盘后再确认', '市场中至少三分之二的股票在跌，暂缓建仓',
  '候选股回落后重新超过昨收、同行同步上涨的',
]);
export const isSpecificDriver = (text: string | null | undefined) => {
  const value = (text || '').trim();
  return value.length >= 10 && !GENERIC_DRIVER_SHORTS.has(value);
};
/** 组头驱动质量：优先「像新闻/事件」的短句（涨跌/订单/发射/政策等），压低泛化信号短语。 */
export function driverScore(entry: Entry) {
  const text = shortDriverOf(entry);
  if (!text) return -1;
  let score = 0;
  if (/[！：:，,]/.test(text)) score += 1;
  if (/涨|跌|走强|逆市|大涨|涨停|订单|发射|签约|获批|发布|收购|业绩|政策|消息|大摩|新闻|利空|利好/.test(text)) score += 2;
  if (isSpecificDriver(text)) score += 2;
  if (/板块上涨|只观察|回踩低吸|加速.高潮|发酵|收盘时已走强|市场中至少|候选股回落/.test(text)) score -= 2;
  return score;
}
/** 代码显示：去 sh/sz/bj 前缀只留 6 位数字（title 保留完整 code）。 */
export function codeDigits(code: string | null | undefined) {
  return String(code || '').replace(/^[A-Za-z]{2}/, '');
}

// ===== 契约 §12.2：按「相关概念/题材」规范归并分组 =====
export const FALLBACK_GROUP = '其他';
export const FALLBACK_NAME_GROUP = '名称辈/生肖';
/** 噪声 token：不作为组键；名称辈/生肖仅作最后兜底。 */
export const NOISE_TOKENS = ['昨日首板', '题材股', '东方财富热股', '热门', '名称', '生肖', '概念'];
export type SynonymGroup = {name: string; keywords: string[]};
/** 同义词组表（顺序即匹配优先级；包含匹配）。 */
export const SYNONYM_GROUPS: SynonymGroup[] = [
  {name: '人形机器人', keywords: ['人形机器人', '机器人', '工业机器人', '机器人执行器', '机器人零部件', '减速器', '精密减速器', '机器视觉', '伺服', '同步磁阻电机', '灵巧手']},
  {name: '商业航天', keywords: ['商业航天', '卫星互联网', '卫星通信', '卫星导航', '航天']},
  {name: 'AI算力', keywords: ['AI硬件', 'AI算力', 'AI服务器', '算力', '数据中心', '存储', '英伟达', '大模型', '物理AI', 'AI']},
  {name: '通信光通信', keywords: ['光通信', '光通信模块', 'CPO', 'F5G', '6G', '通信设备', '通信网络设备及器件', '通信线缆及配套', '通信网络', '通信']},
  {name: '半导体电子', keywords: ['半导体', '芯片', 'OLED', '印制电路板', '元件', '电子']},
  {name: '传媒娱乐', keywords: ['传媒', '传媒娱乐', '游戏', '网络游戏', '影视', '短剧', 'IP', '数字阅读', 'AI漫剧', '快手', '抖音', '超清视频', '在线教育']},
  {name: '低空经济', keywords: ['低空经济']},
  {name: '固态电池', keywords: ['固态电池', '锂电', '电池']},
  {name: '光伏新能源', keywords: ['光伏', '新能源']},
  {name: '汽车产业链', keywords: ['汽车', '智能驾驶']},
  {name: '消费电子', keywords: ['智能穿戴', '虚拟现实', '苹果概念']},
  {name: '化工材料', keywords: ['化工', '钛白粉', '磷肥', '新材', '涤纶', '纳米银', '生物燃料', '玻璃']},
  {name: '能源电力', keywords: ['燃气', '煤炭', '电力', '能源']},
  {name: '家电电机', keywords: ['家电', '卫浴', '电机']},
  {name: '印刷包装', keywords: ['印刷', '包装']},
  {name: '基建', keywords: ['公路', '基建']},
  {name: '农业', keywords: ['农业', '育种', '猪肉', '水产']},
  {name: '消费零售', keywords: ['贸易', '超市', '零售']},
  {name: '可控核聚变', keywords: ['核聚变', '可控核聚变']},
  {name: '冰雪经济', keywords: ['冰雪经济']},
  {name: '核污防治', keywords: ['核污防治']},
];
/** 名称辈/生肖仅当其余 token 都未命中时兜底。 */
export const FALLBACK_SYNONYM: SynonymGroup = {name: FALLBACK_NAME_GROUP, keywords: ['名称辈', '生肖', '东方', '羊年']};
/** 单向包含：token 必须包含分组关键词；避免泛化短词被其它分组的长关键词反向吸走（通信≠卫星通信、能源≠新能源、电机≠同步磁阻电机）。 */
const matchesKeyword = (token: string, keyword: string) => token.includes(keyword);
function matchSynonym(token: string, groups: SynonymGroup[]): string | null {
  for (const group of groups) {
    if (group.keywords.some(keyword => matchesKeyword(token, keyword))) return group.name;
  }
  return null;
}
/** 标签 token 顺序与表格「相关概念·题材」完全一致（同一个 relatedTagsOf，已过滤噪声标签）。 */
function groupTokens(entry: Entry) {
  return relatedTagsOf(entry);
}
/**
 * 分组（用户第六轮修正）：严格按表格「相关概念·题材」的**第一个有效标签**归组。
 * a) 按 tagsOf 显示顺序（theme→concept→event→other）取第一个非噪声标签；
 * b) 命中同义词表 → 规范组名（机器人/减速器→人形机器人、通信→通信光通信…）；
 * c) 未命中 → 直接用该标签本身作组名（东方 / 2027 羊年（跨年）/ 传感器 / 可控核聚变…），
 *    不再统一折叠成「名称辈/生肖」，保证同标签股票同组；
 * d) 无有效标签时才回退 sector（同义词映射，未命中用 sector 本身），最后「其他」。
 */
export function groupKey(entry: Entry): string {
  for (const token of groupTokens(entry)) {
    if (NOISE_TOKENS.includes(token)) continue;
    return matchSynonym(token, SYNONYM_GROUPS) || token;
  }
  const sector = (entry.sector || '').trim();
  if (sector) {
    const matched = matchSynonym(sector, SYNONYM_GROUPS);
    if (matched) return matched;
    if (!NOISE_TOKENS.includes(sector)) return sector;
  }
  return FALLBACK_GROUP;
}
/** 分组一致性审计：逐只校验 groupKey 是否等于「首个显示标签」的规范映射；同一首标签不得分到两个组。 */
export type GroupingIssue = {code: string; name: string; firstTag: string; group: string; expected: string; reason: string};
export function auditGrouping(entries: Entry[]): GroupingIssue[] {
  const issues: GroupingIssue[] = [];
  const tagToGroups = new Map<string, string>();
  for (const entry of entries) {
    const tags = relatedTagsOf(entry);
    const firstTag = tags[0] || '';
    let expected: string;
    if (firstTag) expected = matchSynonym(firstTag, SYNONYM_GROUPS) || firstTag;
    else {
      const sector = String(entry.sector || '').trim();
      const matched = sector ? matchSynonym(sector, SYNONYM_GROUPS) : null;
      expected = matched || (sector && !NOISE_TOKENS.includes(sector) ? sector : FALLBACK_GROUP);
    }
    const group = groupKey(entry);
    if (group !== expected) {
      issues.push({code: entry.code, name: entry.name, firstTag, group, expected, reason: 'group!=first-tag'});
      continue;
    }
    if (firstTag) {
      const previous = tagToGroups.get(firstTag);
      if (previous && previous !== group) {
        issues.push({code: entry.code, name: entry.name, firstTag, group, expected: previous, reason: 'same-tag-split'});
      } else {
        tagToGroups.set(firstTag, group);
      }
    }
  }
  return issues;
}
export type GroupStats = {
  rows: number; up: number; down: number;
  inBuy: number;
  fundYi: number | null;
  driverAt: string | null; driverText: string | null;
};
export type EntryGroup = {key: string; label: string; entries: Entry[]; stats: GroupStats};
function buildGroup(label: string, entries: Entry[], sort: SortState): EntryGroup {
  let up = 0;
  let down = 0;
  let inBuy = 0;
  let fundSum = 0;
  let fundSeen = false;
  let driverAt: string | null = null;
  let driverEntry: Entry | null = null;
  let bestScore = -Infinity;
  let bestAt = '';
  let bestEntry: Entry | null = null;
  for (const entry of entries) {
    if (isNum(entry.today_percent)) {
      if (entry.today_percent > 0) up += 1;
      else if (entry.today_percent < 0) down += 1;
    }
    if (entry.zone === '已进入买区') inBuy += 1;
    const yi = fundYiOf(entry);
    if (yi !== null) { fundSum += yi; fundSeen = true; }
    const at = entry.driver_short_at || driverOf(entry).at;
    if (at && (!driverAt || at > driverAt)) { driverAt = at; driverEntry = entry; }
    const short = shortDriverOf(entry);
    if (short) {
      const score = driverScore(entry);
      const shortAt = entry.driver_short_at || driverOf(entry).at || '';
      if (score > bestScore || (score === bestScore && shortAt > bestAt)) {
        bestScore = score; bestAt = shortAt; bestEntry = entry;
      }
    }
  }
  const driverSource = bestEntry || driverEntry || entries[0] || null;
  const driverText = driverSource ? shortDriverOf(driverSource) : null;
  const finalAt = bestEntry ? (bestEntry.driver_short_at || driverOf(bestEntry).at) : driverAt;
  return {
    key: label, label,
    entries: sortRows(entries, sort),
    stats: {rows: entries.length, up, down, inBuy, fundYi: fundSeen ? Math.round(fundSum * 100) / 100 : null, driverAt: finalAt, driverText},
  };
}
/**
 * 分组（前端计算，契约 §12.2）：
 * - 组键 = groupKey(entry)（同义词归并）；无「其他方向」，全噪声/空归「其他」；
 * - 每组股票数不限（不再合并单只组）；
 * - 组间：资金净流入 desc（缺失最后）→ 组名 asc；组内按当前排序。
 * 入参应为已筛选/搜索后的行，空组自然消失。
 */
export function groupEntries(entries: Entry[], sort: SortState): EntryGroup[] {
  const buckets = new Map<string, Entry[]>();
  for (const entry of entries) {
    const key = groupKey(entry);
    const list = buckets.get(key) ?? [];
    list.push(entry);
    buckets.set(key, list);
  }
  return [...buckets.entries()]
    .map(([label, rows]) => buildGroup(label, rows, sort))
    .sort((left, right) => {
      const lf = left.stats.fundYi;
      const rf = right.stats.fundYi;
      if (lf !== rf) {
        if (lf === null) return 1;
        if (rf === null) return -1;
        return rf - lf;
      }
      return left.label.localeCompare(right.label, 'zh');
    });
}
/** 瀑布流分列：前 N 个组各占一列保证首行即资金 TopN，其余按当前列高贪心放入较矮列（JS masonry，读序近似行优先）。 */
export function layoutGroups(groups: EntryGroup[], columns: number): EntryGroup[][] {
  const count = Math.max(1, Math.min(2, Math.floor(columns) || 1));
  if (count === 1 || groups.length <= 1) return [groups];
  const cols: EntryGroup[][] = Array.from({length: count}, () => []);
  const heights = Array.from({length: count}, () => 0);
  const groupHeight = (group: EntryGroup) => 34 + 24 + group.entries.length * 23 + 8;
  groups.forEach((group, index) => {
    let target = index < count ? index : heights.indexOf(Math.min(...heights));
    cols[target].push(group);
    heights[target] += groupHeight(group);
  });
  return cols;
}
export function groupFundText(value: number | null | undefined) {
  if (!isNum(value)) return '—';
  return (value > 0 ? '+' : '') + value.toFixed(2) + '亿';
}
// ===== 时间范围（按入选日，跳周末） =====
export function previousTradingDay(anchor: string, offset: number) {
  const value = new Date(anchor + 'T00:00:00Z');
  let remaining = Math.max(0, offset);
  while (remaining > 0) {
    value.setUTCDate(value.getUTCDate() - 1);
    const weekday = value.getUTCDay();
    if (weekday !== 0 && weekday !== 6) remaining -= 1;
  }
  return value.toISOString().slice(0, 10);
}
export function periodStart(anchor: string, period: RowPeriod) {
  if (period === 'all') return null;
  if (period === 'today') return anchor;
  return previousTradingDay(anchor, (period === '3d' ? 3 : 5) - 1);
}
export function filterRows(rows: Entry[], filter: RowFilter, anchor: string) {
  const start = periodStart(anchor, filter.period);
  const search = filter.search.trim().toLowerCase();
  return rows.filter(entry => {
    const episodes = episodesOf(entry);
    if (filter.chip === 'today' && !(episodes.today > 0 || entry.added_day === anchor)) return false;
    if (filter.chip === 'multi' && episodes.total < 2) return false;
    if (start && entry.added_day < start) return false;
    if (search) {
      const tags = tagsOf(entry);
      const haystack = [entry.code, entry.name, ...tags.concept, ...tags.theme, ...tags.event, ...tags.other].join(' ').toLowerCase();
      if (!haystack.includes(search)) return false;
    }
    return true;
  });
}
export function rowCounts(rows: Entry[], anchor: string) {
  let today = 0;
  let multi = 0;
  let up = 0;
  let down = 0;
  let flat = 0;
  for (const entry of rows) {
    const episodes = episodesOf(entry);
    if (episodes.today > 0 || entry.added_day === anchor) today += 1;
    if (episodes.total >= 2) multi += 1;
    if (isNum(entry.today_percent) && entry.today_percent > 0) up += 1;
    else if (isNum(entry.today_percent) && entry.today_percent < 0) down += 1;
    else flat += 1;
  }
  return {all: rows.length, today, multi, up, down, flat};
}
const sortValue = (entry: Entry, key: SortKey): number | string | null => {
  switch (key) {
    case 'added': return entry.added_at || entry.added_day || '';
    case 'entry': return entry.added_price;
    case 'since': return entry.since_add_percent;
    case 'today': return entry.today_percent;
    case 'ratio': return quantOf(entry).volume_ratio;
    case 'turnover': return quantOf(entry).turnover_rate;
    case 'episodes': return episodesOf(entry).total;
  }
};
const isEmptySortValue = (value: number | string | null) => value === null || value === undefined || value === '' || (typeof value === 'number' && !Number.isFinite(value));
/** 排序：空值永远排最后（无论升降序）；默认时间降序。 */
export function sortRows(rows: Entry[], sort: SortState) {
  const factor = sort.dir === 'desc' ? -1 : 1;
  return [...rows].sort((left, right) => {
    const a = sortValue(left, sort.key);
    const b = sortValue(right, sort.key);
    const emptyA = isEmptySortValue(a);
    const emptyB = isEmptySortValue(b);
    if (emptyA && emptyB) return String(right.added_day).localeCompare(String(left.added_day));
    if (emptyA) return 1;
    if (emptyB) return -1;
    if (typeof a === 'number' && typeof b === 'number') return (a - b) * factor;
    return String(a).localeCompare(String(b)) * factor;
  });
}
export function toggleSort(sort: SortState, key: SortKey): SortState {
  if (sort.key === key) return {key, dir: sort.dir === 'desc' ? 'asc' : 'desc'};
  return {key, dir: key === 'added' ? 'desc' : 'desc'};
}
export function sortOptionValue(sort: SortState) {
  const found = SORT_OPTIONS.find(option => option.key === sort.key && option.dir === sort.dir);
  return found ? found.value : 'added-desc';
}
export function sortFromOption(value: string): SortState {
  const found = SORT_OPTIONS.find(option => option.value === value);
  return found ? {key: found.key, dir: found.dir} : DEFAULT_SORT;
}

// ===== 详情：窗口表现 =====
export const HORIZONS: ['T+1', 'T+3', 'T+5'] = ['T+1', 'T+3', 'T+5'];
export function windowOf(entry: Entry, key: string): EntryWindow | null {
  if (!entry.windows) return null;
  return (entry.windows[key] as EntryWindow | null) ?? null;
}
export function windowReturnText(entry: Entry, key: string) {
  const window = windowOf(entry, key);
  return window && isNum(window.return_percent) ? (window.return_percent > 0 ? '+' : '') + window.return_percent.toFixed(2) + '%' : '待积累';
}
export function windowExcessText(entry: Entry, key: string) {
  const window = windowOf(entry, key);
  return window && isNum(window.excess_percent) ? (window.excess_percent > 0 ? '+' : '') + window.excess_percent.toFixed(2) + '%' : '待积累';
}
export function planText(plan: Plan | null, key: 'buy' | 'chase' | 'stop' | 'target1' | 'target2' | 'trail') {
  if (!plan) return '—';
  if (key === 'buy') {
    if (isNum(plan.buy_low) && isNum(plan.buy_high)) return num2(plan.buy_low) + '–' + num2(plan.buy_high);
    if (isNum(plan.buy_low)) return '≤' + num2(plan.buy_low);
    if (isNum(plan.buy_high)) return '≥' + num2(plan.buy_high);
    return '—';
  }
  return num2(plan[key]);
}

// ===== 回测（契约 §1.3 / §2.2） =====
export type Horizon = 'T+1' | 'T+3' | 'T+5';
export type BacktestReturn = {date?: string | null; ret_percent?: number | null; bench_percent?: number | null; excess_percent?: number | null; basis?: string | null};
export type BacktestRow = {
  code: string; name: string; source: string; category: string;
  first_day: string; first_price: number; first_percent: number | null; episodes: number;
  latest_day?: string | null; latest_price?: number | null; since_percent?: number | null;
  returns?: Partial<Record<Horizon, BacktestReturn | null>> | null;
  pending?: string[] | null; missing?: string[] | null;
  tags?: Partial<Record<keyof Tags, unknown>> | null;
};
export type BacktestCoverage = {rows?: number; with_returns?: number; bench?: string; daily_codes?: number; episode_issues?: number; episode_range?: string; note?: string};
export type BacktestData = {rows?: BacktestRow[] | null; coverage?: BacktestCoverage | null; error?: string};
export type BacktestFilter = {period: RowPeriod; episodes: 'all' | '1' | '2' | '3+'; percent: 'all' | 'lt0' | '0-3' | '3-7' | '7+'; source: string};
export const DEFAULT_BACKTEST_FILTER: BacktestFilter = {period: 'all', episodes: 'all', percent: 'all', source: '全部'};
export const BACKTEST_EPISODE_OPTIONS: {value: BacktestFilter['episodes']; label: string}[] = [
  {value: 'all', label: '全部天数'}, {value: '1', label: '1 天'}, {value: '2', label: '2 天'}, {value: '3+', label: '3 天及以上'},
];
export const BACKTEST_PERCENT_OPTIONS: {value: BacktestFilter['percent']; label: string}[] = [
  {value: 'all', label: '全部涨幅'}, {value: 'lt0', label: '< 0%'}, {value: '0-3', label: '0–3%'}, {value: '3-7', label: '3–7%'}, {value: '7+', label: '7% 以上'},
];
export const horizonValue = (row: BacktestRow, horizon: Horizon): BacktestReturn | null => row.returns?.[horizon] ?? null;
export type HorizonState = 'done' | 'pending' | 'missing';
export function horizonState(row: BacktestRow, horizon: Horizon): HorizonState {
  if (isNum(horizonValue(row, horizon)?.ret_percent)) return 'done';
  if ((row.missing ?? []).includes(horizon)) return 'missing';
  return 'pending';
}
export function horizonCell(row: BacktestRow, horizon: Horizon) {
  const state = horizonState(row, horizon);
  if (state === 'pending') return {text: '未到期', tone: 'pending'};
  if (state === 'missing') return {text: '缺数据', tone: 'missing'};
  const value = horizonValue(row, horizon)?.ret_percent;
  return {text: pctSigned(value), tone: toneClass(value)};
}
export function horizonTitle(row: BacktestRow, horizon: Horizon) {
  const state = horizonState(row, horizon);
  if (state !== 'done') return horizon === 'T+1' ? 'T+1 尚未到交易日/缺本机日K' : horizon + ' 未到期或日K缺失';
  const item = horizonValue(row, horizon);
  const parts: string[] = [];
  if (item?.date) parts.push(item.date);
  if (isNum(item?.ret_percent)) parts.push('个股 ' + pctSigned(item?.ret_percent));
  if (isNum(item?.bench_percent)) parts.push('基准 ' + pctSigned(item?.bench_percent));
  if (isNum(item?.excess_percent)) parts.push('超额 ' + pctSigned(item?.excess_percent));
  return parts.join(' · ');
}
export function backtestAnchor(rows: BacktestRow[]) {
  let anchor = '';
  for (const row of rows) if (row.first_day && row.first_day > anchor) anchor = row.first_day;
  return anchor;
}
export function backtestSources(rows: BacktestRow[]) {
  const seen = new Set<string>();
  for (const row of rows) if (row.source) seen.add(row.source);
  return [...seen];
}
export function percentBucket(value: number | null) {
  if (!isNum(value)) return 'na';
  if (value < 0) return 'lt0';
  if (value < 3) return '0-3';
  if (value < 7) return '3-7';
  return '7+';
}
export function episodesBucket(value: number | null | undefined) {
  const count = isNum(value) ? value : 1;
  if (count >= 3) return '3+';
  if (count === 2) return '2';
  return '1';
}
export function filterBacktestRows(rows: BacktestRow[], filter: BacktestFilter) {
  const anchor = backtestAnchor(rows);
  const start = periodStart(anchor, filter.period);
  return rows.filter(row => {
    if (start && row.first_day < start) return false;
    if (filter.episodes !== 'all' && episodesBucket(row.episodes) !== filter.episodes) return false;
    if (filter.percent !== 'all' && percentBucket(row.first_percent) !== filter.percent) return false;
    if (filter.source !== '全部' && (row.source || '') !== filter.source) return false;
    return true;
  });
}
export type BucketStat = {key: string; label: string; rows: number; sample: number; upRate: number | null; avgReturn: number | null; avgExcess: number | null};
function statOf(rows: BacktestRow[]): {sample: number; upRate: number | null; avgReturn: number | null; avgExcess: number | null} {
  let sample = 0;
  let up = 0;
  let returnSum = 0;
  let excessSample = 0;
  let excessSum = 0;
  for (const row of rows) {
    const value = horizonValue(row, 'T+1');
    if (isNum(value?.ret_percent)) {
      sample += 1;
      returnSum += value.ret_percent as number;
      if ((value.ret_percent as number) > 0) up += 1;
    }
    if (isNum(value?.excess_percent)) {
      excessSample += 1;
      excessSum += value.excess_percent as number;
    }
  }
  return {
    sample,
    upRate: sample ? Math.round((up / sample) * 1000) / 10 : null,
    avgReturn: sample ? Math.round((returnSum / sample) * 100) / 100 : null,
    avgExcess: excessSample ? Math.round((excessSum / excessSample) * 100) / 100 : null,
  };
}
export type BacktestSummary = {rows: number} & ReturnType<typeof statOf> & {done: number; pending: number; missing: number};
export function backtestSummary(rows: BacktestRow[]): BacktestSummary {
  let done = 0;
  let pending = 0;
  let missing = 0;
  for (const row of rows) {
    const state = horizonState(row, 'T+1');
    if (state === 'done') done += 1;
    else if (state === 'missing') missing += 1;
    else pending += 1;
  }
  return {...statOf(rows), rows: rows.length, done, pending, missing};
}
const bucketRows = (rows: BacktestRow[], keyOf: (row: BacktestRow) => string): Map<string, BacktestRow[]> => {
  const map = new Map<string, BacktestRow[]>();
  for (const row of rows) {
    const key = keyOf(row);
    const list = map.get(key) ?? [];
    list.push(row);
    map.set(key, list);
  }
  return map;
};
function bucketStat(key: string, label: string, items: BacktestRow[]): BucketStat {
  return {key, label, rows: items.length, ...statOf(items)};
}
export function bucketByEpisodes(rows: BacktestRow[]): BucketStat[] {
  const groups = bucketRows(rows, row => episodesBucket(row.episodes));
  return [
    {key: '1', label: '1 天'},
    {key: '2', label: '2 天'},
    {key: '3+', label: '3 天及以上'},
  ].map(item => bucketStat(item.key, item.label, groups.get(item.key) ?? []));
}
export function bucketByPercent(rows: BacktestRow[]): BucketStat[] {
  const groups = bucketRows(rows, row => percentBucket(row.first_percent));
  return [
    {key: 'lt0', label: '< 0%'},
    {key: '0-3', label: '0–3%'},
    {key: '3-7', label: '3–7%'},
    {key: '7+', label: '7% 以上'},
    {key: 'na', label: '缺数据'},
  ].map(item => bucketStat(item.key, item.label, groups.get(item.key) ?? []));
}
/** 按首次入选日分组：取最近 10 个日期。 */
export function bucketByFirstDay(rows: BacktestRow[]): BucketStat[] {
  const groups = bucketRows(rows, row => row.first_day || '');
  return [...groups.keys()].filter(Boolean).sort((left, right) => right.localeCompare(left)).slice(0, 10)
    .map(day => bucketStat(day, day.slice(5), groups.get(day) ?? []));
}
export function backtestCoverageText(coverage: BacktestCoverage | null | undefined) {
  if (!coverage) return '';
  const parts: string[] = [];
  if (isNum(coverage.rows)) parts.push('回测覆盖 ' + coverage.rows + ' 只');
  if (isNum(coverage.with_returns)) parts.push('有收益 ' + coverage.with_returns + ' 只');
  if (coverage.bench) parts.push('基准 ' + coverage.bench);
  if (isNum(coverage.daily_codes)) parts.push('本机日K覆盖 ' + coverage.daily_codes + ' 只');
  if (isNum(coverage.episode_issues)) parts.push('统计范围 ' + coverage.episode_issues + ' 期研判' + (coverage.episode_range ? '（' + coverage.episode_range + '）' : ''));
  return parts.join(' · ');
}
export const backtestTone = (value: number | null | undefined) => toneClass(value);
