export const isPrivatePage=(path:string)=>/^\/(workspace|login|signup|verify-email|forgot-password|reset-password)(\/|$)/.test(path);
