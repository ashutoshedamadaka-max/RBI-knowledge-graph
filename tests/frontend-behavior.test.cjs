const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const elements = new Map();
function element(selector) {
  if (!elements.has(selector)) elements.set(selector, {textContent:'', innerHTML:'', dataset:{},
    classList:{toggle(){}, add(){}, remove(){}}, setAttribute(){}});
  return elements.get(selector);
}
const context = vm.createContext({window:{RBI_API_BASE_URL:''}, document:{querySelector:element,querySelectorAll:()=>[]},
  localStorage:{getItem:()=>null}, Date, Map, Set, Intl});
const script = fs.readFileSync(path.join(__dirname,'../frontend/assets/app.js'),'utf8');
vm.runInContext(script.split("\n$('#query-form').addEventListener")[0], context);
function run(source) {return vm.runInContext(source, context);}
test('counts documents separately from their cited passages', () => {
  assert.equal(run(`sourceGroups([{source_url:'a',chunk_id:'1'},{source_url:'b',chunk_id:'2'},{source_url:'a',chunk_id:'3'}]).length`),2);
  assert.equal(run(`citationMap({citations:[{document_id:'a',chunk_id:'1'},{document_id:'a',chunk_id:'2'}]}).get('2')`),0);
});
test('stale and missing monitoring cannot appear healthy', () => {
  assert.equal(run(`monitoringFreshness('2026-09-18', Date.parse('2026-10-07')).state`),'stale');
  assert.equal(run(`monitoringFreshness(null).state`),'unavailable');
  assert.equal(run(`monitoringFreshness('2026-10-07', Date.parse('2026-10-07')).state`),'recent');
});
test('groups repeated monitoring events without discarding history', () => {
  assert.equal(run(`groupUpdates([{source_url:'a',detected_at:'2026-09-17'},{source_url:'a',detected_at:'2026-09-18'}])[0].length`),2);
  assert.equal(run(`groupUpdates([{source_url:'a',detected_at:'2026-09-17'},{source_url:'a',detected_at:'2026-09-18'}])[0][0].detected_at`),'2026-09-18');
});
test('HTML pages do not claim PDF pagination; removed headings stay removed', () => {
  assert.match(run(`sourceLocation({source_url:'https://rbi.org.in/NotificationUser.aspx',page_number:1})`),/pagination not verified/);
  assert.equal(run(`sourceLocation({source_url:'https://rbi.org.in/a.pdf',page_number:3})`),'PDF page 3');
  assert.doesNotMatch(run(`claimHtml({text:'Healthcare facilities.',title:null,citation_ids:[]},0,new Map())`), /<h4>/);
});
test('answer rendering uses document counts and factual retrieval labels', () => {
  run(`lastQuery='RBI lending rules'; renderAnswer({research:{status:'grounded',direct_answer:{text:'Check evidence.',citation_ids:['a','c']},sections:[]},citations:[{chunk_id:'a',document_id:'one',document_title:'One'},{chunk_id:'b',document_id:'two',document_title:'Two'},{chunk_id:'c',document_id:'one',document_title:'One'}],retrieved_evidence:[],pipeline:{retrieval_method:'vector'},citation_valid:true,latency_ms:1000})`);
  assert.match(element('#evidence-badge').textContent,/2 RBI documents · 3 cited passages/);
  assert.equal(element('#source-tab-count').textContent,'(2)');
  assert.equal(element('#behind-route').textContent,'Text retrieval');
  assert.match(element('#sources-tab').innerHTML,/2 cited passages/);
});
test('unavailable evaluations remain an honest empty state', () => {
  run(`renderEvaluationUnavailable('No report')`);
  assert.equal(element('#evaluation-dataset-note').textContent,'No report');
  assert.match(element('#evaluation-results').innerHTML,/Not yet evaluated/);
});
