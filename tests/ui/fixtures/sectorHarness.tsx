// This reusable legacy component is no longer mounted on the breadth page.
// Exercise its original source/selection contracts without restoring an old UI.
import React from 'react';
import {createRoot} from 'react-dom/client';
import SectorOpportunities from '../../../src/SectorOpportunities';
export function mount(){
  const host=document.createElement('div');document.body.prepend(host);
  const request=async<T,>(method:string,args?:Record<string,unknown>):Promise<T>=>{
    const path=method==='sector_flow'?(args?.kind==='concept'?'/sector-concept-preview.json':'/sector-flow-preview.json'):
      method==='external_market'?'/external-market-preview.json':null;
    if(!path)throw Error('测试未提供 '+method);
    const response=await fetch(path);if(!response.ok)throw Error('fixture unavailable');return response.json() as Promise<T>;
  };
  createRoot(host).render(<SectorOpportunities request={request} preview/>);
}
