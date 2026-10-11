import React from 'react';export default function Link({href,children,prefetch,replace,scroll,...props}:any){return <a href={typeof href==='string'?href:'#'} {...props}>{children}</a>}
