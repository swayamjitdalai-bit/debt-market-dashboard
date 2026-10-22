const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const source=fs.readFileSync('cd_cp_secondary_processorhtml.html','utf8');
const start=source.indexOf('function lineChart('), end=source.indexOf('/* Single-series column chart',start);
const element={style:{},setAttribute(){},addEventListener(){},querySelector(){return this;}};
const host={innerHTML:'',querySelector(){return element;}};
const context={niceTicks:()=>[6,7],esc:s=>s,shortDate:s=>s};
vm.createContext(context);vm.runInContext(source.slice(start,end),context);
context.lineChart(host,{title:'CP',dates:['a','b','c'],series:[
 {name:'3 Months',color:'blue',values:[6.2,null,6.4]},
 {name:'12 Months',color:'red',values:[null,6.8,null]},
 {name:'6 Months',color:'green',values:[null,null,null]}
]});
assert.equal((host.innerHTML.match(/class="observed-point"/g)||[]).length,3);
assert.match(host.innerHTML,/stroke-dasharray="5 4"/);
assert.match(host.innerHTML,/12 Months \(1 observations\)/);
assert.match(host.innerHTML,/6 Months \(0 observations\)/);
assert.doesNotMatch(host.innerHTML,/NaN/);
console.log('Chart rendering: isolated 12M point, gap connector and empty tenor passed');
