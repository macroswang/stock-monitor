export type Bar={time:string;close:string;volume:number;complete:boolean;average?:string|null;high?:string;low?:string};
export type Daily={provisional?:boolean;quote_time?:string;date:string;open:string;close:string;high:string;low:string;volume:string;volume_unit?:string;source?:unknown;cached_at?:string};
export type Event={key:string;symbol:string;name?:string;code?:string;source?:unknown;source_name?:string;trading_date:string;candidate_time:string;confirmation_label:string;event_label:string;volumes:number[];mode:string;kind?:string;delivery?:string|null;local_delivery?:string|null;local_detail?:string;reference_price?:string|null};
export type SourceInfo={selected:string;providers:{id:string;name:string;available:boolean;website:string;description:string}[];quote_time?:string;cache_time?:string;daily_coverage:string[];minute_coverage:string[];quote_url:string;minute_url:string;daily_url:string;history_minute_url?:string};
export type HistoryDay={date:string;status:string;message:string;signal_count:number;recorded_count:number;has_minutes:boolean;limit_up?:string;limit_basis?:string;matches:Event[]};
export type HistoryView={code:string;daily:Daily[];days:HistoryDay[];events:Event[];minute_days:string[];source:SourceInfo};
export type Message={id:string;category:string;title:string;body:string;event_key?:string;created_at:string;read_at?:string;payload:Partial<Event>&{status?:string;detail?:string};local_delivery?:string;local_detail?:string;delivery?:string};

export type IndexQuote={code:string;name:string;price:string;previous_close:string;change:string;percent:string;timestamp:string;source:string};
export type IndexMinute={date:string;previous_close:string;bars:{time:string;close:string}[];cached_at?:string;source?:string};
export type MarketData={quotes:IndexQuote[];minute:IndexMinute|null;error?:string;collected_at?:string};

export type VolumeFlow={code:string;day:string;status:string;source?:string;message:string;updated_at?:string;verified_minutes?:number;approximate_minutes?:number;secondary_minutes?:number;total_only?:boolean;live_fresh?:boolean|null;minutes:{time:string;total:number;buy:number;sell:number;neutral:number;unknown:number;verified:boolean;source?:string|null;source_total?:number;difference?:number;approximate?:boolean}[]};
