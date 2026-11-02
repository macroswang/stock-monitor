import type {ReactNode} from 'react';
import './infoNote.css';

/** Optional methodology belongs behind a consistent, keyboard-accessible link. */
export default function InfoNote({children,label='数据说明',className=''}:{children:ReactNode;label?:string;className?:string}) {
 return <details className={'info-note '+className}>
  <summary><svg viewBox="0 0 20 20" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true"><circle cx="10" cy="10" r="7.5"/><path d="M10 8.5V14m0-9v1"/></svg>{label}</summary>
  <div className="info-note-content">{children}</div>
 </details>;
}
