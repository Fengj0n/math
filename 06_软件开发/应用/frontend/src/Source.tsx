export type SourceRecord = {
  id:string; source?:string; year?:number|null; number?:number|string;
  provenance:string; stage_source?:string;
  question_file?:string; question_path?:string; question_pages?:number[]; question_available?:boolean;
  answer_file?:string; answer_path?:string; answer_pages?:number[]; answer_available?:boolean;
};
let snapshotPromise:Promise<any>|undefined;
export function loadAnalysis(){
  if(!snapshotPromise) snapshotPromise=fetch('/analysis.json',{cache:'no-store'}).then(async r=>{
    if(!r.ok)throw new Error('本地来源索引未加载');return r.json();
  }).catch(e=>{snapshotPromise=undefined;throw e});
  return snapshotPromise;
}
