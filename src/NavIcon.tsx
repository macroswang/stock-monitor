import type {ReactNode} from 'react';
/** Shared 24px line icons keep navigation legible at every sidebar width. */
export default function NavIcon({name}:{name:string}) {
 const paths:Record<string,ReactNode>={
  modes:<><path d="M5 4h14v16H5zM8 8h8M8 12h4m-4 4h6"/></>,
  market:<><path d="M3 3v18h18M6 15l4-5 4 3 6-8"/><path d="M16 5h4v4"/></>,
  breadth:<><path d="M4 20V10m5 10V4m5 16v-7m5 7V7M2 20h20"/></>,
  pool:<><path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="10" cy="18" r="2"/></>,
  paper:<><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h6M9 11h6m-6 5 2 2 4-4"/></>,
  trading:<><path d="M3 7h17m-4-4 4 4-4 4M21 17H4m4-4-4 4 4 4"/></>,
  data:<><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/></>,
  settings:<><path d="M4 7h8m4 0h4M4 17h3m4 0h9"/><circle cx="14" cy="7" r="2"/><circle cx="9" cy="17" r="2"/></>,
  ma250:<><path d="M3 17 8 12l4 3 7-8"/><path d="M3 20h18" strokeDasharray="2 3"/><path d="M15 7h4v4"/></>,
 };
 return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{paths[name]||paths.market}</svg>;
}
