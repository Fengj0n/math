export interface Question {
  id:string; revision:string;origin_id:string;source:string; year:number|null;original_number:number|string;
  subject:string;chapter:string;point:string;model:string;code:string;type:string;original_points:number|null;
  difficulty:number|null;calculation:number|null;integration:string;core:string;method:string;alternative:string;
  stem:string;options:string[];parts:string[];answer:string;solution:string;key:string;errors:string;
  rubric:{step:string;points:number}[];minutes:number|null;category:string;idea:string;provenance:string;
  eligible:boolean;compatibility:boolean;auto_grade_ready:boolean;review:string;render_ready:boolean;source_body_ready:boolean;
  personal_note:string;note_version:number;favorite:boolean;notes:string;
  source_assets:Record<string,{image_path:string;pdf_page:number}[]>;history:{rev:string;created:string}[];
  presentation_issues?:{field:string;reason:string}[];
}
export interface MaterialFilter {search?:string;chapter?:string;subject?:string;type?:string;difficulty?:number|null}
export interface PaperItem {number:number;points:number|null;locked:boolean;question:Question}
export interface Checks {passed:boolean;errors:string[];count:number;points:number;subjects:Record<string,number>}
export interface Design {warnings:string[];pending:string[];chapters?:Record<string,number>;difficulty?:Record<string,number>;minutes_estimate?:number|null;mean_difficulty?:number|null;weighted_difficulty?:number|null;calculation_mean?:number|null;quality_statement?:string}
export interface Paper {id:string;title:string;mode:'standard'|'chapter';version:number;created:string;parent_id?:string;seed?:string;items:PaperItem[];checks:Checks;design:Design;minutes:number|null}
export interface Grade {state:string;score:number|null;origin:string;response:string}
export interface Attempt {id:string;paper_id:string;status:'active'|'paused'|'submitted';version:number;elapsed:number;created:string;responses:Record<string,string>;grades:Record<string,Grade>;paper:Paper;summary?:{automatic_score:number;self_score:number;manual_score:number;pending:number;confirmed_correct:number;confirmed_answered:number}}
export interface Job {id:string;state:string;progress?:number;error?:string;paper_id?:string;files?:{name:string;pages:number;kind:string}[]}
export async function api<T>(url:string,body?:unknown,method?:string):Promise<T>{
  const r=await fetch('/api'+url,{method:method||(body===undefined?'GET':'POST'),headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const value=await r.json();if(!r.ok)throw new Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));return value as T;
}
