/** Exact Decimal comparison; only the final bounded display ratio becomes a Number. */
export function budgetBars(actual:string,plan:string):[number,number]|null{
 if(![actual,plan].every(value=>/^\d{1,30}(\.\d{1,12})?$/.test(value)))return null;
 const decimals=Math.max(...[actual,plan].map(value=>(value.split('.')[1]??'').length));
 const scaled=[actual,plan].map(value=>{const [whole,fraction='']=value.split('.');return BigInt(whole+fraction.padEnd(decimals,'0'));});
 const maximum=scaled[0]>scaled[1]?scaled[0]:scaled[1];
 return maximum===BigInt(0)?[0,0]:scaled.map(value=>Number(value*BigInt(10000)/maximum)/100) as [number,number];
}

/** Display proportions only; categories must form a disjoint, complete partition. */
export function leadShares({total,qualified,unresolved}:{total:number;qualified:number;unresolved:number}):[number,number,number]|null{
 if(![total,qualified,unresolved].every(v=>Number.isSafeInteger(v)&&v>=0)||total===0||qualified+unresolved>total)return null;
 return [qualified/total*100,unresolved/total*100,(total-qualified-unresolved)/total*100];
}
