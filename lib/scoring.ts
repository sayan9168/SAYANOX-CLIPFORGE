export type Signal={hook:number;context:number;emotion:number;visual:number;audio:number;ending:number};
export function score(s:Signal){return Math.round(s.hook*.30+s.context*.25+s.emotion*.15+s.visual*.10+s.audio*.10+s.ending*.10)}
export function rank<T extends Signal>(items:(T&{id:string})[]){return [...items].sort((a,b)=>score(b)-score(a))}