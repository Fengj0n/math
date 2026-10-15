import type {Question} from './types';
export interface AnalysisController {setView(view:string):void;setSelection(ids:string[]):void;dispose():void}
export function mountAnalysis(host:HTMLElement,rows:Question[],options:{view:string;selected:string[];loadQuestion:(id:string)=>Promise<Question>;onView:(view:string)=>void;onOpenQuestion:(id:string)=>void;onAdd:(id:string)=>void;onSelection:()=>void}):AnalysisController;
