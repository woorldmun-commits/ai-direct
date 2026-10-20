type ClassValue = string | false | null | undefined | ClassValue[];

export function cn(...values: ClassValue[]) {
  return (values as unknown[]).flat(Infinity).filter(Boolean).join(" ");
}
