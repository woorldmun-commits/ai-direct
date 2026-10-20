import assert from 'node:assert/strict';
import {budgetBars} from '../lib/chart-geometry.ts';
assert.deepEqual(budgetBars('50.00','100'),[50,100]);
assert.deepEqual(budgetBars('200','100.000'),[100,50]);
assert.deepEqual(budgetBars('0','0.00'),[0,0]);
assert.deepEqual(budgetBars('9007199254740993.01','9007199254740993.01'),[100,100]);
for(const value of ['-1','NaN','Infinity','1e5','1.2.3'])assert.equal(budgetBars(value,'1'),null);
console.log('PASS chart geometry: exact Decimal scaling, zero, large amounts, invalid inputs');
