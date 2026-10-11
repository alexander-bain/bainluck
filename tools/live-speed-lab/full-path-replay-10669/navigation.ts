export const useSearchParams=()=>new URLSearchParams(location.search);
export const usePathname=()=>location.pathname;
export const useRouter=()=>({push:(p:string)=>{location.href=p},replace:(p:string)=>{location.href=p},back:()=>history.back(),prefetch:()=>{}});
export const useParams=()=>({id:document.body.dataset.event});
