export function isPublicDemoFlag(value: string | undefined): boolean {
  return value === "1";
}

export function canUseBackend(publicDemo: boolean): boolean {
  return !publicDemo;
}

export const PUBLIC_DEMO_MODE = isPublicDemoFlag(process.env.NEXT_PUBLIC_HYC_PUBLIC_DEMO);
