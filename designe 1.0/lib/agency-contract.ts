export type AgencyClients={managed:boolean;items:{id:string;name:string;status:string}[]};
export function isAgencyClients(v:unknown):v is AgencyClients {
  if(!v||typeof v!=='object'||!('managed' in v)||typeof v.managed!=='boolean'||!('items' in v)||!Array.isArray(v.items)||v.items.length>5)return false;
  return v.items.every(i=>i&&typeof i==='object'&&typeof i.id==='string'&&/^ws_[1-9]\d{0,18}$/.test(i.id)&&typeof i.name==='string'&&i.name.length<=120&&['active','deactivated','deletion_pending'].includes(i.status));
}
