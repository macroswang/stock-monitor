export type Bar={time:string;close:string;volume:number;complete:boolean;average?:string|null;high?:string;low?:string};
export type Daily={provisional?:boolean;quote_time?:string;date:string;open:string;close:string;high:string;low:string;volume:string;volume_unit?:string;source?:unknown;cached_at?:string};
export type Event={key:string;symbol:string;name?:string;code?:string;source?:unknown;source_name?:string;trading_date:string;candidate_time:string;confirmation_label:string;event_label:string;volumes:number[];mode:string;kind?:string;delivery?:string|null;local_delivery?:string|null;local_detail?:string;reference_price?:string|null};
export type SourceInfo={selected:string;providers:{id:string;name:string;available:boolean;website:string;description:string}[];quote_time?:string;cache_time?:string;daily_coverage:string[];minute_coverage:string[];quote_url:string;minute_url:string;daily_url:string;history_minute_url?:string};
export type HistoryDay={date:string;status:string;message:string;signal_count:number;recorded_count:number;has_minutes:boolean;limit_up?:string;limit_basis?:string;matches:Event[]};
export type Ma250Signal={key?:string;date:string;close:number;ma250:number;ma5:number;distance_pct:number;touch_date:string;touch_low:number;touch_depth_pct:number;pullback_pct:number;stop:number;strong?:boolean;strong_reasons?:string[];market_above?:boolean|null;higher_low?:boolean;prior_low?:number|null;macd_hist?:number;atr20_pct?:number|null;version?:string};
export type Ma250Breakout={date:string;close:number;ma250:number;margin_pct:number;slope60_pct:number|null;volume_ratio:number|null;days_below:number;market_above?:boolean|null;quality?:boolean;kind?:string};
export type Ma250Pullback={signals:Ma250Signal[];breakouts?:Ma250Breakout[];latest?:{date:string;close:number;ma250:number|null;distance_pct:number|null;status:string;bars:number}|null;version?:string;parameters?:Record<string,number>;error?:string|null};
export type E2Signal={key:string;date:string;source_date:string;source_high:number;confirmation_day:number;close:number;ma250:number;ma5:number;distance_pct:number;stop:number;research_only:true};
export type E2Research={signals:E2Signal[];research_only:true;rule_id:string;error?:string|null};
export type HistoryView={code:string;daily:Daily[];days:HistoryDay[];events:Event[];minute_days:string[];ma250?:Ma250Pullback;e2?:E2Research;source:SourceInfo};
export type Message={id:string;category:string;title:string;body:string;event_key?:string;created_at:string;read_at?:string;payload:Partial<Event>&{status?:string;detail?:string;alert_label?:string};local_delivery?:string;local_detail?:string;delivery?:string};

export type IndexQuote={code:string;name:string;price:string;previous_close:string;change:string;percent:string;timestamp:string;source:string};
export type IndexMinute={code?:string;name?:string;date:string;previous_close:string;bars:{time:string;close:string;volume_lots?:number}[];cached_at?:string;source?:string};
export type MarketData={quotes:IndexQuote[];minute:IndexMinute|null;error?:string;collected_at?:string};

export type VolumeFlow={code:string;day:string;status:string;source?:string;message:string;updated_at?:string;verified_minutes?:number;approximate_minutes?:number;secondary_minutes?:number;total_only?:boolean;live_fresh?:boolean|null;minutes:{time:string;total:number;buy:number;sell:number;neutral:number;unknown:number;verified:boolean;source?:string|null;source_total?:number;difference?:number;approximate?:boolean}[]};
