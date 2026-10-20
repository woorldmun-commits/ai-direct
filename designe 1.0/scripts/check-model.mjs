import assert from 'node:assert/strict';
import {campaigns,sum,daily,scoped,cpa,initialState,applyRecommendation,monthlyPrice,seriesFor,restoreState,recs,recommendationsFor,comparisonFor} from '../components/reference/model.ts';
assert.deepEqual(sum(campaigns),{spend:248640,conversions:1284,revenue:3842000,cpa:248640/1284});
assert.equal(cpa(100,0),0);
assert.equal(cpa(0,0),0);
for(const total of [0,1,3,1284,248640,3842000])for(const seed of [0,1,2]){
 const series=daily(total,seed);
 assert.equal(series.length,31);
 assert.equal(series.reduce((a,b)=>a+b,0),total);
 assert(series.every(v=>Number.isInteger(v)&&v>=0));
}
assert.equal(sum(scoped(campaigns,31,'Все аккаунты')).spend,248640);
assert(sum(scoped(campaigns,7,'Все аккаунты')).spend<248640);
assert.equal(sum(scoped(campaigns,31,'Магазин')).spend+sum(scoped(campaigns,31,'Агентство')).spend,248640);
assert.equal(scoped(campaigns,31,'Магазин','Авито').length,0);
const applied=applyRecommendation(initialState,1);
assert.deepEqual(applied.applied,[1]);
assert.equal(applyRecommendation(applied,1),applied);
assert.equal(applyRecommendation(initialState,99),initialState);
assert.equal(initialState.applied.length,0);
assert.equal(monthlyPrice(2990,true),2392);
assert.equal(monthlyPrice(5990,true)*12,57504);
assert.equal(monthlyPrice(9990,false),9990);
console.log('PASS: totals, zero CPA, daily allocation, account/period filters, idempotent apply, annual discount');

assert.equal(restoreState({applied:[99]}),initialState);
assert.equal(restoreState({...initialState,profile:{name:3}}),initialState);
assert.equal(restoreState(initialState),initialState);
for(const days of [1,7,31]){const series=seriesFor(campaigns,days),total=sum(scoped(campaigns,days,'Все аккаунты'));for(const key of ['spend','conversions','revenue'])assert.equal(series[key].reduce((a,b)=>a+b,0),total[key]);}
console.log('PASS: restored state validation and chart/table/KPI consistency');

const fullRecommendations=recommendationsFor(campaigns);
assert.equal(fullRecommendations.reduce((a,r)=>a+r.effect,0),244840);
assert.deepEqual(recommendationsFor(scoped(campaigns,31,'Агентство')).map(r=>r.id),[3]);
assert.deepEqual(recommendationsFor(scoped(campaigns,31,'Магазин')).map(r=>r.id),[1,2]);
assert.deepEqual(recommendationsFor([]),[]);
for(const days of [1,7,31])for(const account of ['Магазин','Агентство','Все аккаунты']){
 const rows=scoped(campaigns,days,account);
 for(const r of recommendationsFor(rows)){
  const row=rows.find(c=>c.id===r.campaignId),base=recs.find(c=>c.id===r.id),campaign=campaigns.find(c=>c.id===r.campaignId);
  assert.equal(r.effect,Math.round(base.effect*row.spend/campaign.spend));
  if(r.kind==='saving')assert(r.effect<=row.spend,'Savings must not exceed scoped campaign spend');
 }
 const series=seriesFor(campaigns.filter(c=>account==='Все аккаунты'||c.account===account),days),total=sum(rows);
 for(const key of ['spend','conversions','revenue'])assert.equal(series[key].reduce((a,b)=>a+b,0),total[key]);
 const comparison=comparisonFor(rows);
 for(const key of ['spend','conversions','cpa','revenue'])assert.equal(comparison.changes[key],Math.round((total[key]/comparison.previous[key]-1)*100));
}
assert.deepEqual(comparisonFor([]).changes,{spend:null,conversions:null,cpa:null,revenue:null});
assert.equal(comparisonFor([{...campaigns[0],conversions:0}]).changes.cpa,null);
console.log('PASS: scoped recommendation identities/effects, bounded savings, nine chart/KPI slices, modeled deltas and empty evidence');
