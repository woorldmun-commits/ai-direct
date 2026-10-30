// A closed route list prevents this server-side session bridge becoming an arbitrary HTTP proxy.
export function workspacePath(path: string, method: string): boolean {
 if(path==='/billing/plans')return method==='GET';
 if(/^\/workspaces\/ws_[1-9]\d{0,18}\/billing\/orders\/current$/.test(path))return method==='GET';
 const base='/workspaces/ws_[1-9]\\d{0,18}';
 if(method==='GET')return new RegExp('^'+base+'/(campaign-stats\\?days=(?:7|30)(?:&ad_account=acc_[1-9]\\d{0,18}(?:&campaign_id=[1-9]\\d{0,18})?)?(?:&offset=\\d{1,5})?|today|insights|members|subscription|intelligence(?:/(?:snapshot-analysis|chief-analyst)(?:\\?days=(?:7|30))?|/imports/[0-9a-fA-F-]{36}|\\?cursor=[0-9a-fA-F-]{36})?|weekly-report|recommendation-activity(?:\\?cursor=[1-9]\\d{0,18})?|recommendations(?:/rec_[1-9]\\d{0,18}|\\?limit=50(?:&cursor=o\\d{1,9})?)?)$').test(path);
 return method==='POST'&&new RegExp('^'+base+'/(billing/orders(?:/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/(?:checkout|refresh))?|budget-plan|intelligence/(profile|import|analyze|decisions)|lead-import(?:/preview)?|recommendations/rec_[1-9]\\d{0,18}/(decisions|manual-execution|verification))$').test(path);
}
