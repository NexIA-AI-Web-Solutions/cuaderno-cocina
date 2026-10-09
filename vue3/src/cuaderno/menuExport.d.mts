import type {PrintedMenus, EntityImage} from './planningApi'
export const MAX_EXPORT_PAGES: number
export interface ExportLine {text: string; y: number; kind: string; unsuitable?: boolean}
export interface ExportPage {width:number;height:number;lines:ExportLine[];image:EntityImage|null;imageY:number;imageHeight:number}
export function wrapText(value: unknown,width:number,measure:(s:string)=>number):string[]
export function layoutMenu(doc:PrintedMenus,measure:(s:string)=>number):ExportPage[]
export function encodeMenuPdf(images:{jpeg:Uint8Array;width:number;height:number}[],orientation:string):Uint8Array
