export const isPrivatePage=(path:string)=>/^\/(app|workspace|onboarding|login|signup|register|verify-email|forgot-password|reset-password)(\/|$)/.test(path);
