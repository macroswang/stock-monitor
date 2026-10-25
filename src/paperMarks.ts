export type PaperFillPoint={stamp:string;side:'buy'|'sell';shares:number;amount:number;fills:number};
export type PaperChartMark={time:string;price:number;value:'B'|'S'|'T';buyShares:number;sellShares:number;buyAmount:number;sellAmount:number;fills:number};
export function paperChartMarks(points:PaperFillPoint[],daily=false):PaperChartMark[]{
 const groups=new Map<string,PaperChartMark>();
 for(const p of points){
  if(!Number.isFinite(p.shares)||p.shares<=0||!Number.isFinite(p.amount)||p.amount<=0||!['buy','sell'].includes(p.side))continue;
  const time=daily?p.stamp.slice(0,10):p.stamp.slice(11,16),key=daily?time:time+'|'+p.side;
  const m=groups.get(key)||{time,price:0,value:p.side==='buy'?'B':'S',buyShares:0,sellShares:0,buyAmount:0,sellAmount:0,fills:0};
  if(p.side==='buy'){m.buyShares+=p.shares;m.buyAmount+=p.amount;}else{m.sellShares+=p.shares;m.sellAmount+=p.amount;}
  m.fills+=p.fills;m.value=m.buyShares&&m.sellShares?'T':m.buyShares?'B':'S';
  m.price=(m.buyAmount+m.sellAmount)/(m.buyShares+m.sellShares)/100;
  groups.set(key,m);
 }
 return [...groups.values()].sort((a,b)=>a.time.localeCompare(b.time)||a.value.localeCompare(b.value));
}
