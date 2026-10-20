// A closed route list prevents this server-side session bridge becoming an arbitrary HTTP proxy.
export function workspacePath(path: string, method: string): boolean {
 const base='/workspaces/ws_[1-9]\\d{0,18}';
 if(method==='GET')return new RegExp('^'+base+'/(today|insights|recommendations(?:/rec_[1-9]\\d{0,18}|\\?limit=50(?:&cursor=o\\d{1,9})?)?)$').test(path);
 return method==='POST'&&new RegExp('^'+base+'/(budget-plan|lead-import|recommendations/rec_[1-9]\\d{0,18}/(decisions|manual-execution|verification))$').test(path);
}
