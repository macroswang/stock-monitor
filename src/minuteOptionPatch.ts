type Series = {id?:string|number;name?:unknown};
export type MinuteOption = Record<string,unknown> & {series:Series[]};
type Dependencies = Record<string,unknown>;
const signature=(value:unknown)=>JSON.stringify(value,(_key,item)=>typeof item==='function'?String(item):item);

/** Bounded display cache. Never cache prices beyond the supplied reached data. */
export class MinuteOptionPatch {
 private components=new Map<string,string|undefined>();
 private series=new Map<string,string|undefined>();
 constructor(option:MinuteOption,dependencies:Dependencies){this.capture(option,dependencies);}
 private capture(option:MinuteOption,dependencies:Dependencies){
  this.components.clear();this.series.clear();
  for(const [key,value] of Object.entries(option))if(key!=='series')this.components.set(key,signature([value,dependencies[key]]));
  for(const item of option.series)this.series.set(String(item.id),signature([item,dependencies[String(item.id)]]));
 }
 next(option:MinuteOption,dependencies:Dependencies){
  const patch:Record<string,unknown>={};
  for(const [key,value] of Object.entries(option)){
   // The current zoom belongs to the user, not the arriving quote snapshot.
   if(key==='series'||key==='dataZoom')continue;
   if(this.components.get(key)!==signature([value,dependencies[key]]))patch[key]=value;
  }
  const ids=option.series.map(item=>String(item.id));
  const replaced=ids.length!==this.series.size||ids.some(id=>!this.series.has(id));
  const changed=replaced?option.series:option.series.filter(item=>this.series.get(String(item.id))!==signature([item,dependencies[String(item.id)]]));
  if(changed.length||replaced)patch.series=changed;
  this.capture(option,dependencies);
  return {option:patch,replaceSeries:replaced};
 }
}
